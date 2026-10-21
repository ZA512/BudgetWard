"""Explicit account association and atomic, user-confirmed bank imports."""

import csv
import io
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .connectors import ConnectorAccount, ConnectorTransaction
from .csv_import import CsvCommit, CsvInput
from .csv_import import commit as commit_csv
from .csv_import import preview as preview_csv
from .models import Account, BankBinding
from .woob_connector import MESSAGES, BankConfiguration, ConnectorError, WoobConnector


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


def public_time(value):
    return value.isoformat() + "Z" if value else None


def account_state(account):
    return (account.id, account.balance_cents, account.balance_date.isoformat())


class DemoConnector:
    """Fictional accounts only. Never reads bank credentials or makes a network request."""

    def __init__(self, _):
        pass

    def get_accounts(self):
        return [
            ConnectorAccount(
                id="demo-current-charges",
                name="Compte CHARGES fictif",
                balance_cents=497000,
                masked_iban="•••• 1001",
            ),
            ConnectorAccount(
                id="demo-current-expenses",
                name="Compte DÉPENSES fictif",
                balance_cents=53500,
                masked_iban="•••• 1002",
            ),
        ]

    def read_snapshot(self, account_ids, since, until):
        self.month = until.replace(day=1)

    def get_balance(self, account_id):
        return next(a.balance_cents for a in self.get_accounts() if a.id == account_id)

    def get_transactions(self, account_id, since, until):
        expenses = account_id.endswith("expenses")
        candidates = (
            [
                (min(5, until.day), -16150, "PRLV EDF DÉMONSTRATION", "edf"),
                (min(10, until.day), -27000, "VIR VERS COMPTE DÉPENSES FICTIF", "funding"),
            ]
            if not expenses
            else [
                (min(10, until.day), 27000, "VIR DEPUIS COMPTE CHARGES FICTIF", "incoming"),
                (min(11, until.day), -25800, "COURSES DÉMONSTRATION", "groceries"),
            ]
        )
        return [
            ConnectorTransaction(
                booking_date=until.replace(day=day),
                amount_cents=amount,
                raw_label=label,
                provider_id=f"demo-{self.month}-{code}",
            )
            for day, amount, label, code in candidates
            if since <= until.replace(day=day) <= until
        ]


class Banking:
    def __init__(self, engine, signing_key, *, demo=False, configuration=None, factory=None):
        self.engine, self.signing_key, self.demo = engine, signing_key, demo
        # Demo mode never loads any real server secret.
        self.configuration = (
            configuration
            if configuration is not None
            else (BankConfiguration() if demo else BankConfiguration.from_environment())
        )
        self.factory = factory or (DemoConnector if demo else WoobConnector)
        self.lock = threading.Lock()
        self.choices = {}
        self.snapshots = {}
        self.discovery_error = None
        self.last_network_attempt = None
        self.cooldown_seconds = 0 if demo else 60

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "Une lecture bancaire est déjà en cours.")
        try:
            yield
        finally:
            self.lock.release()

    def status(self):
        with Session(self.engine) as db:
            accounts = {a.id: a for a in db.scalars(select(Account))}
            bindings = list(db.scalars(select(BankBinding)))
            return {
                "demo": self.demo,
                "provider": "Banque fictive" if self.demo else "Crédit Agricole",
                "credentials_configured": self.demo or self.configuration.credentials_configured,
                "module_installed": self.demo or self.configuration.module_installed,
                "running": self.lock.locked(),
                "pending": self.pending() is not None,
                "discovery_error": MESSAGES.get(self.discovery_error),
                "bindings": [
                    {
                        "account_id": b.account_id,
                        "role": accounts[b.account_id].role,
                        "name": accounts[b.account_id].name,
                        "masked_iban": b.masked_iban,
                        "last_attempt_at": public_time(b.last_attempt_at),
                        "last_success_at": public_time(b.last_success_at),
                        "error_code": b.error_code,
                        "error": MESSAGES.get(b.error_code),
                    }
                    for b in bindings
                ],
            }

    def pending(self):
        snapshots = list(self.snapshots.values())
        return (
            snapshots[-1]["public"]
            if snapshots and snapshots[-1]["expires"] > time.monotonic()
            else None
        )

    def discover(self):
        with self.exclusive():
            try:
                accounts = self.factory(self.configuration).get_accounts()
                accounts = [ConnectorAccount.model_validate(a) for a in accounts]
                if len({a.id for a in accounts}) != len(accounts) or len(accounts) > 100:
                    raise ConnectorError("data")
                self.choices = {}
                result = []
                for account in accounts:
                    token = secrets.token_urlsafe(32)
                    self.choices[token] = (time.monotonic() + 600, account)
                    result.append(
                        {
                            "choice_id": token,
                            "name": account.name,
                            "balance_cents": account.balance_cents,
                            "masked_iban": account.masked_iban,
                        }
                    )
                self.discovery_error = None
                return {"accounts": result, "expires_in_seconds": 600, "demo": self.demo}
            except Exception as error:
                code = error.code if isinstance(error, ConnectorError) else "data"
                self.discovery_error = code
                raise ConnectorError(code) from None

    def choice(self, token):
        choice = self.choices.get(token)
        if not choice or choice[0] <= time.monotonic():
            raise HTTPException(
                409, "Le choix bancaire a expiré. Rechargez les comptes puis choisissez à nouveau."
            )
        return choice[1]

    def bind_in_session(self, db, charges_choice, expenses_choice):
        if expenses_choice and charges_choice == expenses_choice:
            raise HTTPException(422, "CHARGES et DÉPENSES doivent être deux comptes différents.")
        selected = {"CHARGES": self.choice(charges_choice)}
        if expenses_choice:
            selected["DEPENSES"] = self.choice(expenses_choice)
        for role, item in selected.items():
            local = db.scalar(select(Account).where(Account.role == role))
            if local is None:
                raise HTTPException(409, "Créez d'abord le suivi de vos comptes.")
            old = db.get(BankBinding, local.id)
            other = db.scalar(
                select(BankBinding).where(
                    BankBinding.provider_account_id == item.id,
                    BankBinding.account_id != local.id,
                )
            )
            if other or (old and old.provider_account_id != item.id):
                raise HTTPException(
                    409,
                    "Un autre compte est déjà associé à ce suivi. "
                    "Utilisez une base distincte pour changer de compte bancaire.",
                )
            if old is None:
                db.add(
                    BankBinding(
                        account_id=local.id,
                        provider_account_id=item.id,
                        masked_iban=item.masked_iban,
                    )
                )
        db.flush()

    def bind(self, charges_choice, expenses_choice):
        with self.exclusive(), Session(self.engine) as db:
            self.bind_in_session(db, charges_choice, expenses_choice)
            db.commit()
            self.snapshots.clear()
        return self.status()

    def record_error(self, code):
        with Session(self.engine) as db:
            for binding in db.scalars(select(BankBinding)):
                binding.error_code = code
            db.commit()

    def prepare(self, since: date, until: date, today: date):
        if until != today or since > until or (until - since).days > 732:
            raise HTTPException(
                422,
                "Choisissez une date de début dans les deux dernières années. "
                "La lecture va jusqu'à aujourd'hui.",
            )
        with self.exclusive():
            if self.last_network_attempt is not None and (
                time.monotonic() - self.last_network_attempt < self.cooldown_seconds
            ):
                raise HTTPException(429, "Patientez une minute entre deux lectures bancaires.")
            self.snapshots.clear()
            with Session(self.engine) as db:
                bindings = list(db.scalars(select(BankBinding).order_by(BankBinding.account_id)))
                if not bindings:
                    raise HTTPException(409, "Associez d'abord le compte CHARGES à votre banque.")
                selected = [(b.account_id, b.provider_account_id, b.masked_iban) for b in bindings]
                states = {id: account_state(db.get(Account, id)) for id, _, _ in selected}
                for binding in bindings:
                    binding.last_attempt_at = utc_now()
                db.commit()
            self.last_network_attempt = time.monotonic()
            try:
                connector = self.factory(self.configuration)
                connector.read_snapshot([provider for _, provider, _ in selected], since, until)
                prepared, public = {}, []
                for id, provider, masked in selected:
                    balance = connector.get_balance(provider)
                    if type(balance) is not int or not -1_000_000_000 <= balance <= 1_000_000_000:
                        raise ConnectorError("data")
                    txs = [
                        ConnectorTransaction.model_validate(t)
                        for t in connector.get_transactions(provider, since, until)
                    ]
                    if len(txs) > 5000 or any(not since <= t.booking_date <= until for t in txs):
                        raise ConnectorError("data")
                    stream = io.StringIO()
                    writer = csv.writer(stream, delimiter=";", lineterminator="\n")
                    writer.writerow(["date", "label", "amount", "reference", "operation_date"])
                    for tx in txs:
                        sign = "-" if tx.amount_cents < 0 else ""
                        amount = (
                            f"{sign}{abs(tx.amount_cents) // 100}.{abs(tx.amount_cents) % 100:02d}"
                        )
                        writer.writerow(
                            [
                                tx.booking_date.isoformat(),
                                tx.raw_label,
                                amount,
                                tx.provider_id or "",
                                tx.operation_date.isoformat() if tx.operation_date else "",
                            ]
                        )
                    body = (
                        CsvInput(
                            account_id=id,
                            content=stream.getvalue(),
                            delimiter=";",
                            date_format="%Y-%m-%d",
                            decimal_separator=".",
                            mapping={
                                "booking_date": "date",
                                "raw_label": "label",
                                "amount": "amount",
                                "provider_id": "reference",
                                "operation_date": "operation_date",
                            },
                        )
                        if txs
                        else None
                    )
                    with Session(self.engine) as db:
                        result = (
                            preview_csv(db, body, today, self.signing_key)
                            if body
                            else {
                                "rows": [],
                                "counts": {},
                                "preview_token": "",
                                "already_imported": False,
                            }
                        )
                        account = db.get(Account, id)
                        public.append(
                            {
                                "account_id": id,
                                "name": account.name,
                                "role": account.role,
                                "masked_iban": masked,
                                "balance_cents": balance,
                                "previous_balance_cents": states[id][1],
                                "preview": result,
                            }
                        )
                    prepared[id] = {
                        "body": body,
                        "preview": result,
                        "balance_cents": balance,
                        "provider": provider,
                        "state": states[id],
                    }
                token = secrets.token_urlsafe(32)
                public_result = {
                    "snapshot_id": token,
                    "accounts": public,
                    "balance_date": until.isoformat(),
                    "since": since.isoformat(),
                    "demo": self.demo,
                    "expires_in_seconds": 600,
                }
                self.snapshots[token] = {
                    "expires": time.monotonic() + 600,
                    "prepared": prepared,
                    "balance_date": until,
                    "since": since,
                    "public": public_result,
                }
                self.record_error(None)
                return public_result
            except Exception as error:
                code = error.code if isinstance(error, ConnectorError) else "data"
                self.record_error(code)
                raise ConnectorError(code) from None

    def commit(self, token, decisions, confirmed, today):
        if not confirmed:
            raise HTTPException(422, "Confirmez l'import et la mise à jour des soldes affichés.")
        with self.exclusive(), Session(self.engine) as db:
            snapshot = self.snapshots.get(token)
            if not snapshot or snapshot["expires"] <= time.monotonic():
                raise HTTPException(409, "L'aperçu bancaire a expiré. Relancez la lecture.")
            prepared = snapshot["prepared"]
            if set(decisions) - {str(id) for id in prepared}:
                raise HTTPException(422, "Décisions pour un compte absent de l'aperçu.")
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            result = []
            for id, item in prepared.items():
                binding, account = db.get(BankBinding, id), db.get(Account, id)
                if (
                    binding is None
                    or binding.provider_account_id != item["provider"]
                    or (account_state(account) != item["state"])
                ):
                    raise HTTPException(
                        409, "Le suivi ou le solde a changé depuis l'aperçu. Relancez la lecture."
                    )
                imported = {"imported_count": 0, "skipped_count": 0}
                if item["body"] is not None:
                    request = CsvCommit(
                        **item["body"].model_dump(),
                        preview_token=item["preview"]["preview_token"],
                        decisions=decisions.get(str(id), {}),
                    )
                    imported = commit_csv(
                        db,
                        request,
                        today,
                        self.signing_key,
                        manage_transaction=False,
                        source="DEMO_BANK" if self.demo else "WOOB",
                    )
                elif decisions.get(str(id)):
                    raise HTTPException(422, "Aucune décision n'est attendue pour ce compte vide.")
                account.balance_cents = item["balance_cents"]
                account.balance_date = snapshot["balance_date"]
                binding.last_success_at, binding.error_code = utc_now(), None
                result.append(
                    {
                        "account_id": id,
                        "imported_count": imported["imported_count"],
                        "skipped_count": imported["skipped_count"],
                    }
                )
            db.commit()
            self.snapshots.pop(token, None)
            return {
                "accounts": result,
                "balance_date": snapshot["balance_date"].isoformat(),
                "imported_count": sum(r["imported_count"] for r in result),
            }

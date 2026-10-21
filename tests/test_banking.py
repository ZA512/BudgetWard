import json
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from woob.capabilities.bank import Account as WoobAccount
from woob.capabilities.bank import Transaction as WoobTransaction
from woob.capabilities.base import NotAvailable
from woob.exceptions import BrowserIncorrectPassword

from budgetward.api import create_app
from budgetward.banking import DemoConnector
from budgetward.connectors import ConnectorAccount, ConnectorTransaction
from budgetward.woob_connector import BankConfiguration, ConnectorError, WoobConnector
from budgetward.woob_worker import collect, euro_cents

TODAY = date(2026, 10, 21)


class FakeConnector:
    failure = None
    balances = {"private-charges-123456789": 470000, "private-expenses-987654321": 35500}

    def __init__(self, configuration):
        self.configuration = configuration

    def get_accounts(self):
        return [
            ConnectorAccount(id=id, name=name, masked_iban=masked, balance_cents=self.balances[id])
            for id, name, masked in [
                ("private-charges-123456789", "Compte joint principal", "•••• 1001"),
                ("private-expenses-987654321", "Compte cartes", "•••• 1002"),
            ]
        ]

    def read_snapshot(self, ids, since, until):
        assert len(ids) in (1, 2)
        if self.failure:
            if isinstance(self.failure, str):
                raise ConnectorError(self.failure)
            raise self.failure

    def get_balance(self, id):
        return self.balances[id]

    def get_transactions(self, id, since, until):
        rows = [(-16150, "EDF", "bank-edf"), (-27000, "VIR DÉPENSES", "bank-fund")]
        if "expenses" in id:
            rows = [(27000, "VIR CHARGES", "bank-incoming"), (-25800, "COURSES", "bank-groceries")]
        return [
            ConnectorTransaction(
                booking_date=TODAY.replace(day=5),
                amount_cents=amount,
                raw_label=label,
                provider_id=provider,
            )
            for amount, label, provider in rows
        ]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("budgetward.api.today", lambda: TODAY)
    FakeConnector.failure = None
    app = create_app(str(tmp_path / "bank.db"), demo=True, bank_factory=FakeConnector)
    with TestClient(app) as c:
        c.headers["x-csrf-token"] = "demo"
        yield c


def associate(c, expenses=True):
    result = c.post("/api/bank/discover")
    assert result.status_code == 200, result.text
    choices = result.json()["accounts"]
    response = c.post(
        "/api/bank/bind",
        json={
            "charges_choice_id": choices[0]["choice_id"],
            "expenses_choice_id": choices[1]["choice_id"] if expenses else None,
            "confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    return choices


def prepare(c):
    response = c.post("/api/bank/preview", json={"since": "2026-10-01"})
    assert response.status_code == 200, response.text
    return response.json()


def confirm(c, view, decisions=None):
    return c.post(
        "/api/bank/commit",
        json={"snapshot_id": view["snapshot_id"], "confirmed": True, "decisions": decisions or {}},
    )


def test_discovery_is_explicit_masked_and_has_no_database_side_effect(client):
    data = client.post("/api/bank/discover").json()
    assert len(data["accounts"]) == 2
    assert "private-charges-123456789" not in json.dumps(data)
    assert not client.get("/api/bank/status").json()["bindings"]
    assert client.get("/api/export").json()["transactions"] == []
    assert client.get("/api/export").json()["accounts"][0]["balance_cents"] == 497000


def test_binding_rejects_same_account_and_expired_choices_without_partial_write(client):
    choices = client.post("/api/bank/discover").json()["accounts"]
    data = {
        "charges_choice_id": choices[0]["choice_id"],
        "expenses_choice_id": choices[0]["choice_id"],
        "confirmed": True,
    }
    assert client.post("/api/bank/bind", json=data).status_code == 422
    bank = client.app.state.banking
    token = choices[1]["choice_id"]
    _, item = bank.choices[token]
    bank.choices[token] = (time.monotonic() - 1, item)
    data["expenses_choice_id"] = token
    assert client.post("/api/bank/bind", json=data).status_code == 409
    assert not client.get("/api/bank/status").json()["bindings"]


def test_cannot_swap_roles_or_replace_an_already_associated_account(client):
    associate(client)
    choices = client.post("/api/bank/discover").json()["accounts"]
    assert (
        client.post(
            "/api/bank/bind",
            json={
                "charges_choice_id": choices[1]["choice_id"],
                "expenses_choice_id": choices[0]["choice_id"],
                "confirmed": True,
            },
        ).status_code
        == 409
    )
    bindings = client.get("/api/bank/status").json()["bindings"]
    assert next(b for b in bindings if b["role"] == "CHARGES")["masked_iban"] == "•••• 1001"


def test_two_accounts_import_only_after_confirmation_and_reimport_has_no_duplicates(client):
    associate(client)
    view = prepare(client)
    assert client.get("/api/export").json()["transactions"] == []
    assert client.get("/api/forecast?month=2026-10").json()["bank_pending"]
    assert client.get("/api/bank/pending").json()["snapshot_id"] == view["snapshot_id"]
    result = confirm(client, view)
    assert result.status_code == 200, result.text
    assert result.json()["imported_count"] == 4
    exported = client.get("/api/export").json()
    assert len(exported["transactions"]) == 4
    assert exported["accounts"][0]["balance_cents"] == 470000
    assert exported["accounts"][1]["balance_cents"] == 35500
    assert not exported["classifications"]  # A transfer is not guessed from its amount or label.
    assert all(t["source"] == "DEMO_BANK" for t in exported["transactions"])
    assert not client.get("/api/forecast?month=2026-10").json()["bank_pending"]
    second = prepare(client)
    assert confirm(client, second).json()["imported_count"] == 0
    assert len(client.get("/api/export").json()["transactions"]) == 4
    for binding in client.get("/api/bank/status").json()["bindings"]:
        assert binding["last_success_at"]
    assert "private-charges-123456789" not in json.dumps(client.get("/api/bank/status").json())


def test_a_conflict_on_second_account_rolls_back_first_account_and_both_balances(client):
    associate(client)
    assert (
        client.post(
            "/api/transactions",
            json={
                "account_id": 2,
                "booking_date": "2026-10-05",
                "amount_cents": 123,
                "raw_label": "VIR CHARGES",
                "provider_id": "bank-incoming",
            },
        ).status_code
        == 200
    )
    view = prepare(client)
    response = confirm(client, view)
    assert response.status_code == 422
    exported = client.get("/api/export").json()
    assert len(exported["transactions"]) == 1
    assert not exported["import_batches"]
    assert exported["accounts"][0]["balance_cents"] == 497000
    assert exported["accounts"][1]["balance_cents"] == 53500
    assert all(not b["last_success_at"] for b in client.get("/api/bank/status").json()["bindings"])


def test_preview_refuses_manual_balance_change_and_stale_import_decisions(client):
    associate(client)
    view = prepare(client)
    client.put(
        "/api/accounts/1",
        json={"name": "Charges", "balance_cents": 480000, "balance_date": "2026-10-21"},
    )
    assert confirm(client, view).status_code == 409
    assert client.get("/api/export").json()["transactions"] == []
    view = prepare(client)
    client.post(
        "/api/transactions",
        json={
            "account_id": 1,
            "booking_date": "2026-10-05",
            "amount_cents": -16150,
            "raw_label": "EDF",
            "provider_id": "bank-edf",
        },
    )
    assert confirm(client, view).status_code == 409
    assert len(client.get("/api/export").json()["transactions"]) == 1


def test_snapshot_expiration_and_missing_confirmation(client):
    associate(client)
    view = prepare(client)
    assert (
        client.post(
            "/api/bank/commit", json={"snapshot_id": view["snapshot_id"], "confirmed": False}
        ).status_code
        == 422
    )
    client.app.state.banking.snapshots[view["snapshot_id"]]["expires"] = time.monotonic() - 1
    assert confirm(client, view).status_code == 409
    assert client.get("/api/bank/pending").json() is None


@pytest.mark.parametrize(
    "code", ["credentials", "action_required", "timeout", "unavailable", "data"]
)
def test_bank_failures_keep_previous_success_and_never_import_a_partial_snapshot(client, code):
    associate(client)
    assert confirm(client, prepare(client)).status_code == 200
    before = client.get("/api/bank/status").json()["bindings"][0]["last_success_at"]
    FakeConnector.failure = code
    response = client.post("/api/bank/preview", json={"since": "2026-10-01"})
    assert response.status_code == 502
    assert response.json()["code"] == code
    binding = client.get("/api/bank/status").json()["bindings"][0]
    assert binding["error_code"] == code
    assert binding["last_success_at"] == before
    assert client.get("/api/forecast?month=2026-10").json()["bank_problem_count"] == 2
    assert len(client.get("/api/export").json()["transactions"]) == 4
    assert client.get("/api/session").json()["authenticated"]


def test_unexpected_provider_error_does_not_expose_its_message(client):
    associate(client)
    FakeConnector.failure = RuntimeError("FAKE-PRIVATE-BANK-LOGIN FAKE-PRIVATE-BANK-PASSWORD")
    response = client.post("/api/bank/preview", json={"since": "2026-10-01"})
    assert response.status_code == 502
    assert "FAKE-PRIVATE" not in response.text
    assert "FAKE-PRIVATE" not in client.get("/api/bank/status").text


def test_demo_never_reads_real_environment_credentials_or_starts_woob(client, monkeypatch):
    monkeypatch.setenv("BUDGETWARD_BANK_LOGIN_FILE", "should-not-be-read")
    monkeypatch.setenv("BUDGETWARD_BANK_PASSWORD_FILE", "should-not-be-read")
    monkeypatch.setattr(
        "budgetward.woob_connector.secret_file", lambda _: pytest.fail("secret read")
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("bank subprocess"))
    app = create_app(str(client.app.state.engine.url.database) + ".other", demo=True)
    with TestClient(app) as demo:
        demo.headers["x-csrf-token"] = "demo"
        associate(demo)
        assert confirm(demo, prepare(demo)).status_code == 200
        assert isinstance(app.state.banking.factory(BankConfiguration()), DemoConnector)


def test_real_bank_status_does_not_contact_provider_and_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("unexpected bank access"))
    app = create_app(
        str(tmp_path / "real.db"),
        "test-admin-token-more-than-24-chars",
        bank_configuration=BankConfiguration(),
    )
    with TestClient(app) as c:
        assert c.get("/api/bank/status").status_code == 401
        session = c.post(
            "/api/session", json={"token": "test-admin-token-more-than-24-chars"}
        ).json()
        c.headers["x-csrf-token"] = session["csrf"]
        status = c.get("/api/bank/status").json()
        assert not status["credentials_configured"]
        assert c.post("/api/bank/discover").json()["code"] == "configuration"


def test_network_read_is_serialized_and_rate_limited(client):
    associate(client)
    bank = client.app.state.banking
    bank.lock.acquire()
    try:
        assert client.post("/api/bank/discover").status_code == 409
    finally:
        bank.lock.release()
    bank.cooldown_seconds = 60
    prepare(client)
    assert client.post("/api/bank/preview", json={"since": "2026-10-01"}).status_code == 429


def test_bank_association_at_setup_is_atomic_and_does_not_erase_an_existing_setup(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("budgetward.api.today", lambda: TODAY)
    app = create_app(
        str(tmp_path / "setup.db"),
        "test-admin-token-more-than-24-chars",
        bank_factory=FakeConnector,
        bank_configuration=BankConfiguration(),
    )
    with TestClient(app) as c:
        login = c.post("/api/session", json={"token": "test-admin-token-more-than-24-chars"}).json()
        c.headers["x-csrf-token"] = login["csrf"]
        choices = c.post("/api/bank/discover").json()["accounts"]
        setup = {
            "name": "Charges",
            "balance_cents": 470000,
            "balance_date": "2026-10-21",
            "expenses_name": "Dépenses",
            "expenses_balance_cents": 35500,
            "charges_choice_id": choices[0]["choice_id"],
            "expenses_choice_id": "expired",
            "bank_confirmed": True,
        }
        assert c.post("/api/setup", json=setup).status_code == 409
        assert c.get("/api/export").json()["accounts"] == []
        setup["expenses_choice_id"] = choices[1]["choice_id"]
        assert c.post("/api/setup", json=setup).status_code == 200
        assert len(c.get("/api/bank/status").json()["bindings"]) == 2
        assert c.post("/api/setup", json=setup).status_code == 409


def test_schema_v2_migrates_with_backup_before_adding_bank_table(tmp_path):
    path = tmp_path / "v2.db"
    with TestClient(create_app(str(path), demo=True)):
        pass
    with closing(sqlite3.connect(path)) as db:
        db.executescript("DROP TABLE bank_bindings; PRAGMA user_version=2;")
        db.commit()
    with TestClient(create_app(str(path), demo=True)) as c:
        assert len(c.get("/api/export").json()["accounts"]) == 2
    copy = next((tmp_path / "backups" / "v2.db" / "before-migration").glob("v2-*.db"))
    with closing(sqlite3.connect(copy)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM accounts").fetchone()[0] == 2


def bank_account(id="private-1", kind=WoobAccount.TYPE_CHECKING):
    account = WoobAccount(id)
    account.type, account.currency, account.label = kind, "EUR", "Compte courant"
    account.balance, account.iban = Decimal("4700.29"), "FR7612345678901234567890123"
    return account


def test_woob_collect_uses_only_current_eur_accounts_and_inclusive_unordered_history():
    account = bank_account()
    foreign = bank_account("foreign")
    foreign.currency = "USD"
    txs = []
    for id, day in [("recent", 10), ("old", 1), ("boundary", 5)]:
        tx = WoobTransaction(id)
        tx.date, tx.rdate, tx.raw, tx.amount = (
            date(2026, 10, day),
            date(2026, 10, day),
            "Carte",
            Decimal("-29.99"),
        )
        txs.append(tx)
    pending = WoobTransaction("pending")
    pending.coming = True
    txs.append(pending)
    backend = SimpleNamespace(
        iter_accounts=lambda: [
            account,
            foreign,
            bank_account("savings", WoobAccount.TYPE_SAVINGS),
            bank_account("card", WoobAccount.TYPE_CARD),
        ],
        iter_history=lambda _: txs,
    )
    accounts = collect(backend, {"operation": "accounts"})
    assert len(accounts) == 1
    assert accounts[0]["masked_iban"] == "•••• 0123"
    result = collect(
        backend,
        {
            "operation": "snapshot",
            "account_ids": ["private-1"],
            "since": "2026-10-05",
            "until": "2026-10-21",
        },
    )
    assert [t["provider_id"] for t in result["private-1"]["transactions"]] == ["recent", "boundary"]
    assert result["private-1"]["balance_cents"] == 470029


@pytest.mark.parametrize(
    "value", [1.23, True, NotAvailable, Decimal("NaN"), Decimal("Infinity"), Decimal("0.001")]
)
def test_woob_rejects_floats_missing_or_inexact_money(value):
    with pytest.raises(ConnectorError):
        euro_cents(value)


@pytest.fixture
def configuration(tmp_path):
    (tmp_path / "cragr").mkdir()
    (tmp_path / "cragr" / "module.py").touch()
    return BankConfiguration("www.ca-paris.fr", "fake-login-never-used", "fake-password", tmp_path)


def test_worker_secrets_are_stdin_only_and_failures_are_sanitized(configuration, monkeypatch):
    def run(command, **kwargs):
        assert configuration.password not in " ".join(command)
        assert json.loads(kwargs["input"])["password"] == configuration.password
        assert kwargs["timeout"] == 180
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"ok": False, "error": "credentials", "message": configuration.password}
            ),
            stderr=configuration.password,
        )

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ConnectorError) as error:
        WoobConnector(configuration).get_accounts()
    assert error.value.code == "credentials"
    assert configuration.password not in str(error.value)
    assert configuration.password not in repr(configuration)


def test_worker_timeout_does_not_expose_subprocess_output(configuration, monkeypatch):
    def run(*a, **k):
        raise subprocess.TimeoutExpired(["fake-private-value"], 180, output="fake-private-value")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ConnectorError) as error:
        WoobConnector(configuration).get_accounts()
    assert error.value.code == "timeout"
    assert "fake-private-value" not in str(error.value)


def test_worker_maps_authentication_errors_without_bank_details(monkeypatch, capsys):
    import io

    import budgetward.woob_worker as worker

    monkeypatch.setattr(worker.sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(
        worker, "execute", lambda _: (_ for _ in ()).throw(BrowserIncorrectPassword("fake-private"))
    )
    worker.main()
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error": "credentials"}

"""Conservative, explainable historical groupings. Never validates a rule automatically."""

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Account,
    BankTransaction,
    Charge,
    ChargeRule,
    Classification,
    HistoryDismissal,
)


def normalized(label: str) -> str:
    text = unicodedata.normalize("NFKD", label)
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())


def rounded_ratio(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def median(values: list[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return (
        ordered[middle]
        if len(ordered) % 2
        else rounded_ratio(ordered[middle - 1] + ordered[middle], 2)
    )


def analyze(db: Session, account_id: int, include_dismissed: bool = False):
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Compte introuvable.")
    all_txs = list(
        db.scalars(
            select(BankTransaction)
            .where(BankTransaction.account_id == account_id)
            .order_by(BankTransaction.booking_date, BankTransaction.id)
        )
    )
    classified = set(db.scalars(select(Classification.transaction_id)))
    dismissals = set(db.scalars(select(HistoryDismissal.key)))
    buckets = defaultdict(list)
    for tx in all_txs:
        if tx.amount_cents < 0 and tx.id not in classified:
            buckets[normalized(tx.raw_label)].append(tx)
    groups = []
    for label, txs in buckets.items():
        key = hashlib.sha256(f"{account_id}:{label}".encode()).hexdigest()
        dismissed = key in dismissals
        if dismissed and not include_dismissed:
            continue
        amounts = [abs(t.amount_cents) for t in txs]
        months = [t.booking_date.year * 12 + t.booking_date.month for t in txs]
        intervals = [
            (b.booking_date - a.booking_date).days for a, b in zip(txs, txs[1:], strict=False)
        ]
        monthly = len(txs) >= 2 and all(
            b - a == 1 for a, b in zip(months, months[1:], strict=False)
        )
        weekly = len(txs) >= 3 and all(5 <= gap <= 9 for gap in intervals)
        fortnightly = len(txs) >= 3 and all(12 <= gap <= 16 for gap in intervals)
        frequency = (
            "MONTHLY"
            if monthly
            else "WEEKLY"
            if weekly
            else ("EVERY_2_WEEKS" if fortnightly else None)
        )
        ambiguous = bool(re.match(r"^(CHEQUE|CHQ|CHECK|VIREMENT|VIR\b|RETRAIT)", label))
        if ambiguous:
            frequency = None
        explanation = (
            "Libellé ambigu : le bénéficiaire et le rôle doivent être identifiés manuellement."
            if ambiguous
            else "Une opération dans chacun de plusieurs mois consécutifs."
            if monthly
            else "Intervalles proches d'une semaine."
            if weekly
            else "Intervalles proches de deux semaines."
            if fortnightly
            else "Historique insuffisant ou irrégulier : aucune fréquence déduite."
        )
        groups.append(
            {
                "key": key,
                "label": txs[-1].raw_label,
                "normalized_label": label,
                "account_id": account_id,
                "count": len(txs),
                "dismissed": dismissed,
                "frequency": frequency,
                "ambiguous": ambiguous,
                "explanation": explanation,
                "first_date": txs[0].booking_date.isoformat(),
                "last_date": txs[-1].booking_date.isoformat(),
                "last_cents": amounts[-1],
                "mean_cents": rounded_ratio(sum(amounts), len(amounts)),
                "median_cents": median(amounts),
                "min_cents": min(amounts),
                "max_cents": max(amounts),
                "total_cents": sum(amounts),
                "interval_days": intervals,
                "transactions": [
                    {
                        "id": t.id,
                        "date": t.booking_date.isoformat(),
                        "raw_label": t.raw_label,
                        "amount_cents": t.amount_cents,
                    }
                    for t in txs
                ],
            }
        )
    groups.sort(key=lambda g: (g["frequency"] is None, -g["count"], g["label"]))
    return {
        "account_id": account_id,
        "transaction_count": len(all_txs),
        "unclassified_debit_count": sum(len(v) for v in buckets.values()),
        "groups": groups,
        "first_date": all_txs[0].booking_date.isoformat() if all_txs else None,
        "last_date": all_txs[-1].booking_date.isoformat() if all_txs else None,
    }


class HistoryValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    account_id: StrictInt
    key: str
    transaction_ids: Annotated[list[StrictInt], Field(min_length=1, max_length=5000)]
    existing_charge_id: StrictInt | None = None
    name: Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]
    amount_cents: Annotated[StrictInt, Field(ge=0, le=1_000_000_000)]
    frequency: Literal["MONTHLY", "WEEKLY", "EVERY_2_WEEKS", "QUARTERLY", "YEARLY"]
    anchor_date: date


def validate(db: Session, data: HistoryValidation):
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    analysis = analyze(db, data.account_id, include_dismissed=True)
    group = next((g for g in analysis["groups"] if g["key"] == data.key), None)
    if group is None:
        raise HTTPException(409, "Ce groupe n'est plus disponible. Actualisez l'analyse.")
    selected = set(data.transaction_ids)
    if len(selected) != len(data.transaction_ids) or not selected.issubset(
        {t["id"] for t in group["transactions"]}
    ):
        raise HTTPException(409, "La sélection a changé ou contient une opération déjà affectée.")
    if data.existing_charge_id is not None:
        charge = db.get(Charge, data.existing_charge_id)
        if charge is None:
            raise HTTPException(404, "Charge introuvable.")
    else:
        charge = Charge(name=data.name)
        db.add(charge)
        db.flush()
        db.add(
            ChargeRule(
                charge_id=charge.id,
                effective_from=data.anchor_date,
                amount_cents=data.amount_cents,
                frequency=data.frequency,
                anchor_date=data.anchor_date,
                tolerance_cents=0,
            )
        )
    for id in selected:
        db.add(Classification(transaction_id=id, kind="CHARGE", charge_id=charge.id))
    dismissal = db.get(HistoryDismissal, data.key)
    if dismissal:
        db.delete(dismissal)
    db.commit()
    return {"charge_id": charge.id, "classified_count": len(selected)}

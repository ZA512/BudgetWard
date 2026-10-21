"""CSV preview and atomic import. Ambiguous matches always require a human choice."""

import csv
import hashlib
import hmac
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Account, BankTransaction, ImportBatch


class CsvMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_date: str
    raw_label: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    operation_date: str | None = None
    provider_id: str | None = None


class CsvInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: StrictInt
    content: Annotated[str, Field(min_length=1, max_length=2_000_000)]
    delimiter: Literal[";", ",", "\t"] = ";"
    date_format: Literal["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"] = "%d/%m/%Y"
    decimal_separator: Literal[",", "."] = ","
    mapping: CsvMapping


class CsvCommit(CsvInput):
    preview_token: str
    decisions: dict[str, Literal["IMPORT", "SKIP"]] = Field(default_factory=dict)


class CsvColumnsInput(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=2_000_000)]
    delimiter: Literal[";", ",", "\t"] = ";"


def columns(data: CsvColumnsInput):
    try:
        reader = csv.reader(
            io.StringIO(data.content.lstrip("\ufeff")), delimiter=data.delimiter, strict=True
        )
        headers = next(reader)
        if not headers or len(headers) > 128 or len(set(headers)) != len(headers):
            raise ValueError("Les en-têtes doivent être distincts (128 colonnes maximum).")
        sample = []
        for _ in range(3):
            row = next(reader, None)
            if row is None:
                break
            sample.append(row)
        return {"headers": headers, "sample": sample}
    except (ValueError, csv.Error, StopIteration) as error:
        raise HTTPException(422, str(error) or "CSV vide ou invalide.") from None


def money_cents(value: str, decimal_separator: str) -> int:
    value = re.sub(r"[\s\u00a0\u202f]", "", value).replace("€", "")
    pattern = r"[+-]?\d+(?:" + re.escape(decimal_separator) + r"\d{1,2})?"
    if not re.fullmatch(pattern, value):
        raise ValueError(
            "Montant invalide : vérifier la virgule ou le point décimal (2 décimales maximum)."
        )
    negative = value.startswith("-")
    whole, _, fraction = value.lstrip("+-").partition(decimal_separator)
    result = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if result > 1_000_000_000:
        raise ValueError("Montant trop élevé.")
    return -result if negative else result


def signature(booking_date: date, amount_cents: int, raw_label: str, operation_date: date | None):
    return (
        booking_date.isoformat(),
        amount_cents,
        raw_label,
        operation_date.isoformat() if operation_date else None,
    )


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def parse(data: CsvInput, today: date):
    try:
        reader = csv.reader(
            io.StringIO(data.content.lstrip("\ufeff")), delimiter=data.delimiter, strict=True
        )
        headers = next(reader)
        if not headers or len(headers) > 128 or len(set(headers)) != len(headers):
            raise ValueError("Les en-têtes doivent être distincts (128 colonnes maximum).")
        mapping = data.mapping.model_dump()
        mapped = [v for v in mapping.values() if v is not None]
        if any(not v or v not in headers for v in mapped):
            raise ValueError("Une colonne sélectionnée est absente du CSV.")
        if len(set(mapped)) != len(mapped):
            raise ValueError("Chaque colonne doit avoir un seul rôle.")
        if bool(data.mapping.amount) == bool(data.mapping.debit or data.mapping.credit):
            raise ValueError("Choisir un montant signé OU des colonnes débit/crédit.")
        rows = []
        for values in reader:
            if not values or not any(v.strip() for v in values):
                continue
            line = reader.line_num
            row = {"line": line, "status": "NEW", "message": "Nouvelle opération"}
            if len(rows) >= 5000:
                raise ValueError("Le fichier dépasse 5 000 opérations. Découpez-le avant import.")
            try:
                if len(values) != len(headers):
                    raise ValueError("Nombre de colonnes différent de l'en-tête.")
                source = dict(zip(headers, values, strict=True))

                def cell(field, source=source):
                    name = mapping[field]
                    return source[name].strip() if name else ""

                def parsed_date(value):
                    try:
                        result = datetime.strptime(value, data.date_format).date()
                    except ValueError:
                        raise ValueError("Date invalide pour le format sélectionné.") from None
                    if result > today:
                        raise ValueError("Une opération réelle ne peut pas être future.")
                    return result

                booking = parsed_date(cell("booking_date"))
                operation = parsed_date(cell("operation_date")) if cell("operation_date") else None
                if operation and operation > booking:
                    raise ValueError("La date d'achat est postérieure à la date comptable.")
                label = cell("raw_label")
                if not label or len(label) > 250:
                    raise ValueError("Le libellé doit contenir de 1 à 250 caractères.")
                provider_id = cell("provider_id") or None
                if provider_id and len(provider_id) > 120:
                    raise ValueError("La référence bancaire dépasse 120 caractères.")
                if data.mapping.amount:
                    amount = money_cents(cell("amount"), data.decimal_separator)
                else:
                    debit = money_cents(cell("debit") or "0", data.decimal_separator)
                    credit = money_cents(cell("credit") or "0", data.decimal_separator)
                    if debit < 0 or credit < 0 or (debit and credit):
                        raise ValueError("Débit/crédit : un seul montant positif par ligne.")
                    amount = credit - debit
                if amount == 0:
                    raise ValueError("Le montant ne peut pas être nul.")
                row.update(
                    booking_date=booking.isoformat(),
                    operation_date=operation.isoformat() if operation else None,
                    amount_cents=amount,
                    raw_label=label,
                    provider_id=provider_id,
                )
            except ValueError as error:
                row.update(status="ERROR", message=str(error))
            rows.append(row)
        if not rows:
            raise ValueError("Le CSV ne contient aucune opération.")
        return headers, rows
    except (ValueError, csv.Error, StopIteration) as error:
        raise HTTPException(422, str(error) or "CSV vide ou invalide.") from None


def preview(db: Session, data: CsvInput, today: date, signing_key: bytes):
    if db.get(Account, data.account_id) is None:
        raise HTTPException(404, "Compte introuvable.")
    headers, rows = parse(data, today)
    payload = data.model_dump(exclude={"preview_token", "decisions"})
    digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
    receipt = db.scalar(
        select(ImportBatch).where(
            ImportBatch.account_id == data.account_id, ImportBatch.digest == digest
        )
    )
    existing = list(
        db.scalars(select(BankTransaction).where(BankTransaction.account_id == data.account_id))
    )
    ids = {t.provider_id: t for t in existing if t.provider_id}
    signatures = defaultdict(list)
    for tx in existing:
        signatures[signature(tx.booking_date, tx.amount_cents, tx.raw_label, None)[:3]].append(tx)
    seen_ids = {}
    for row in rows:
        if row["status"] == "ERROR":
            continue
        sig = (row["booking_date"], row["amount_cents"], row["raw_label"], row["operation_date"])
        provider = row["provider_id"]
        if provider and provider in seen_ids:
            if seen_ids[provider] != sig:
                row.update(
                    status="CONFLICT", message="Référence répétée avec des données différentes."
                )
            else:
                row.update(
                    status="DUPLICATE", message="Même référence déjà présente dans ce fichier."
                )
        elif provider and provider in ids:
            tx = ids[provider]
            # A later export may add an operation date; originals remain immutable.
            if (tx.booking_date.isoformat(), tx.amount_cents, tx.raw_label) != sig[:3]:
                row.update(
                    status="CONFLICT",
                    message="Cette référence existe avec un montant, "
                    "une date ou un libellé différent. Vérifiez le relevé.",
                )
            else:
                row.update(status="DUPLICATE", message="Référence bancaire déjà importée.")
        elif receipt:
            row.update(status="DUPLICATE", message="Ce fichier avec ce mapping a déjà été traité.")
        elif matches := [
            t.id
            for t in signatures[sig[:3]]
            if (not provider or not t.provider_id)
            and (
                not row["operation_date"]
                or not t.operation_date
                or t.operation_date.isoformat() == row["operation_date"]
            )
        ]:
            row.update(
                status="AMBIGUOUS",
                message="Opération similaire déjà présente : "
                "choisir de la conserver ou de l'écarter.",
                matching_ids=sorted(matches),
            )
        if provider:
            seen_ids[provider] = sig
    counts = dict(Counter(row["status"] for row in rows))
    token = hmac.new(
        signing_key, canonical({"digest": digest, "rows": rows}).encode(), hashlib.sha256
    ).hexdigest()
    dates = [r["booking_date"] for r in rows if "booking_date" in r]
    return {
        "headers": headers,
        "rows": rows,
        "counts": counts,
        "already_imported": bool(receipt),
        "digest": digest,
        "preview_token": token,
        "date_from": min(dates) if dates else None,
        "date_until": max(dates) if dates else None,
    }


def commit(
    db: Session,
    data: CsvCommit,
    today: date,
    signing_key: bytes,
    *,
    manage_transaction: bool = True,
    source: str = "CSV",
):
    # Serialize the read/check/write sequence, including imports without bank references.
    if manage_transaction:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    result = preview(db, data, today, signing_key)
    receipt = db.scalar(
        select(ImportBatch).where(
            ImportBatch.account_id == data.account_id, ImportBatch.digest == result["digest"]
        )
    )
    if receipt:
        return {
            "imported_count": 0,
            "skipped_count": len(result["rows"]),
            "already_imported": True,
            "transaction_ids": [],
            "date_from": result["date_from"],
            "date_until": result["date_until"],
        }
    if not hmac.compare_digest(data.preview_token, result["preview_token"]):
        raise HTTPException(409, "Les données ont changé. Recalculez l'aperçu avant de valider.")
    if any(r["status"] in {"ERROR", "CONFLICT"} for r in result["rows"]):
        raise HTTPException(
            422, "Corrigez les lignes invalides avant d'importer. Rien n'a été ajouté."
        )
    ambiguous = {str(r["line"]) for r in result["rows"] if r["status"] == "AMBIGUOUS"}
    if set(data.decisions) != ambiguous:
        raise HTTPException(422, "Choisissez une décision pour chaque doublon possible.")
    added, skipped = [], 0
    for row in result["rows"]:
        if row["status"] == "DUPLICATE" or data.decisions.get(str(row["line"])) == "SKIP":
            skipped += 1
            continue
        tx = BankTransaction(
            account_id=data.account_id,
            provider_id=row["provider_id"],
            booking_date=date.fromisoformat(row["booking_date"]),
            operation_date=date.fromisoformat(row["operation_date"])
            if row["operation_date"]
            else None,
            amount_cents=row["amount_cents"],
            raw_label=row["raw_label"],
            source=source,
        )
        db.add(tx)
        added.append(tx)
    try:
        db.flush()
        transaction_ids = [t.id for t in added]
        db.add(
            ImportBatch(
                account_id=data.account_id,
                digest=result["digest"],
                imported_count=len(added),
                skipped_count=skipped,
                transaction_ids=transaction_ids,
            )
        )
        if manage_transaction:
            db.commit()
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Un autre import a modifié les données. Recalculez l'aperçu."
        ) from None
    return {
        "imported_count": len(added),
        "skipped_count": skipped,
        "already_imported": False,
        "transaction_ids": transaction_ids,
        "date_from": result["date_from"],
        "date_until": result["date_until"],
    }

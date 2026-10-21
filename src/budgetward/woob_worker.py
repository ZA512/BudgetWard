"""Only iter_accounts/iter_history are exposed. No storage, payment or bank transfer API."""

import contextlib
import json
import logging
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal

from woob.capabilities.bank import Account
from woob.capabilities.base import empty
from woob.core import WoobBase
from woob.exceptions import (
    ActionNeeded,
    AppValidation,
    BrowserIncorrectPassword,
    BrowserQuestion,
    NeedInteractive,
)
from woob.tools.backend import Module

from .woob_connector import ConnectorError


def euro_cents(value):
    if empty(value) or isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise ConnectorError("data")
    amount = Decimal(value) * 100
    if (
        not amount.is_finite()
        or amount != amount.to_integral_value()
        or abs(amount) > 1_000_000_000
    ):
        raise ConnectorError("data")
    return int(amount)


def bank_date(value, optional=False):
    if empty(value) and optional:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise ConnectorError("data")
    return value.isoformat()


def account_data(account):
    iban = getattr(account, "iban", None)
    name = re.sub(
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,}\b|\d{8,}",
        lambda match: "•••• " + match.group()[-4:],
        str(account.label),
    )
    return {
        "id": str(account.id),
        "name": name,
        "balance_cents": euro_cents(account.balance),
        "masked_iban": "•••• " + str(iban)[-4:]
        if not empty(iban)
        else "Compte •••• " + str(account.id)[-4:],
    }


def collect(backend, request):
    accounts = [
        a
        for a in backend.iter_accounts()
        if a.type == Account.TYPE_CHECKING and a.currency == "EUR" and not empty(a.label)
    ]
    if request["operation"] == "accounts":
        return [account_data(a) for a in accounts]
    if request["operation"] != "snapshot":
        raise ConnectorError("data")
    selected = request["account_ids"]
    if set(selected) - {str(a.id) for a in accounts}:
        raise ConnectorError("account")
    start, end = date.fromisoformat(request["since"]), date.fromisoformat(request["until"])
    result = {}
    for account in accounts:
        if str(account.id) not in selected:
            continue
        transactions = []
        for item in backend.iter_history(account):
            if getattr(item, "coming", False) is True:
                continue
            booked = bank_date(item.date)
            if not start <= date.fromisoformat(booked) <= end:
                continue  # Provider order is not guaranteed; never stop at the first older row.
            currency = getattr(item, "currency", None)
            if not empty(currency) and currency != "EUR":
                raise ConnectorError("data")
            raw = item.raw if not empty(item.raw) else item.label
            if empty(raw):
                raise ConnectorError("data")
            transactions.append(
                {
                    "booking_date": booked,
                    "operation_date": bank_date(getattr(item, "rdate", None), optional=True),
                    "amount_cents": euro_cents(item.amount),
                    "raw_label": str(raw),
                    "provider_id": str(item.id) if not empty(item.id) else None,
                }
            )
            if len(transactions) > 5000:
                raise ConnectorError("data")
        result[str(account.id)] = {
            "balance_cents": euro_cents(account.balance),
            "transactions": transactions,
        }
    return result


def execute(request):
    core = WoobBase(modules_path=request["modules_path"])
    try:
        try:
            backend = core.load_backend(
                "cragr",
                "budgetward",
                params={
                    "website": request["website"],
                    "login": request["login"],
                    "password": request["password"],
                },
            )
        except Module.ConfigError:
            raise ConnectorError("configuration") from None
        return collect(backend, request)
    finally:
        core.deinit()


def main():
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.read())
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            data = execute(request)
        response = {"ok": True, "data": data}
    except ConnectorError as error:
        response = {"ok": False, "error": error.code}
    except BrowserIncorrectPassword:
        response = {"ok": False, "error": "credentials"}
    except (ActionNeeded, AppValidation, BrowserQuestion, NeedInteractive):
        response = {"ok": False, "error": "action_required"}
    except Exception:
        response = {"ok": False, "error": "unavailable"}
    print(json.dumps(response))


if __name__ == "__main__":
    main()

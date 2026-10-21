from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import month_bounds, occurrences, totals
from .models import (
    Account,
    Adjustment,
    BankTransaction,
    Budget,
    Charge,
    ChargeRule,
    Classification,
    Plan,
)


def forecast(db: Session, month: str, today: date):
    start, end = month_bounds(month)
    accounts = list(db.scalars(select(Account).order_by(Account.id)))
    account_map = {a.id: a for a in accounts}
    charges_account = next((a for a in accounts if a.role == "CHARGES"), None)
    plan = db.get(Plan, month)
    safety, goal = (plan.safety_cents, plan.treasury_cents) if plan else (0, 0)
    txs = list(db.scalars(select(BankTransaction).order_by(BankTransaction.booking_date.desc())))
    classified = {c.transaction_id: c for c in db.scalars(select(Classification))}
    charge_rows, budget_rows, anomalies = [], [], []
    for charge in db.scalars(select(Charge).order_by(Charge.name)):
        rules = list(db.scalars(select(ChargeRule).where(ChargeRule.charge_id == charge.id)))
        expected = []
        for rule in rules:
            dates = occurrences(
                month, rule.frequency, rule.anchor_date, rule.end_date, rule.installment_count
            )
            expected.extend(
                (d, rule)
                for d in dates
                if rule.effective_from <= d
                and (rule.effective_until is None or d <= rule.effective_until)
            )
        expected.sort(key=lambda pair: pair[0])
        paid = sorted(
            [
                t
                for t in txs
                if start <= t.booking_date <= end
                and (c := classified.get(t.id))
                and c.charge_id == charge.id
            ],
            key=lambda t: (t.booking_date, t.id),
        )
        all_paid = paid
        first_rule_date = min(r.effective_from for r in rules)
        paid = [t for t in all_paid if t.booking_date >= first_rule_date]
        remaining = expected[len(paid) :]
        expected_sum = sum(r.amount_cents for _, r in expected)
        remaining_sum = sum(r.amount_cents for _, r in remaining)
        status = "PAID" if expected and not remaining else "PLANNED"
        if not expected and all_paid and not paid:
            status = "HISTORICAL"
        for index, tx in enumerate(paid):
            if index >= len(expected):
                anomalies.append(
                    {
                        "key": f"extra-{tx.id}",
                        "title": charge.name,
                        "message": "Paiement supplémentaire ou après la fin prévue.",
                        "transaction_id": tx.id,
                    }
                )
                status = "REVIEW"
                continue
            _, rule = expected[index]
            if abs(abs(tx.amount_cents) - rule.amount_cents) > rule.tolerance_cents:
                anomalies.append(
                    {
                        "key": f"amount-{tx.id}",
                        "title": charge.name,
                        "message": "Montant payé différent de la règle. "
                        "Le paiement est pris en compte ; la règle reste inchangée.",
                        "expected_cents": rule.amount_cents,
                        "actual_cents": abs(tx.amount_cents),
                        "transaction_id": tx.id,
                    }
                )
                status = "REVIEW"
            if account_map[tx.account_id].role != "CHARGES":
                anomalies.append(
                    {
                        "key": f"account-{tx.id}",
                        "title": charge.name,
                        "message": "Charge payée sur un compte autre que CHARGES.",
                        "transaction_id": tx.id,
                    }
                )
                status = "REVIEW"
        # First lot: a due date is an indication, not an invented banking payment window.
        if (
            status != "REVIEW"
            and remaining
            and remaining[0][0] < min(today, end)
            and start <= today
        ):
            status = "EXPECTED"
        latest = max(rules, key=lambda r: r.effective_from)
        charge_rows.append(
            {
                "id": charge.id,
                "name": charge.name,
                "status": status,
                "expected_cents": expected_sum,
                "paid_cents": sum(abs(t.amount_cents) for t in all_paid),
                "remaining_cents": remaining_sum,
                "count": len(expected),
                "dates": [d.isoformat() for d, _ in expected],
                "amount_cents": latest.amount_cents,
                "frequency": latest.frequency,
                "anchor_date": latest.anchor_date.isoformat(),
                "end_date": latest.end_date.isoformat() if latest.end_date else None,
                "installment_count": latest.installment_count,
                "tolerance_cents": latest.tolerance_cents,
                "rule_count": len(rules),
                "explanation": f"{len(expected)} échéance(s) prévue(s). "
                f"{len(paid)} paiement(s) pris en compte pour ces échéances. "
                f"{len(all_paid) - len(paid)} paiement(s) antérieur(s) au début de la règle "
                "conservé(s) comme historique réel. "
                "Les échéances payées ne sont plus protégées sur CHARGES.",
            }
        )
    for budget in db.scalars(select(Budget).order_by(Budget.name)):
        dates = occurrences(month, budget.frequency, budget.anchor_date)
        override = (plan.budget_counts or {}).get(str(budget.id)) if plan else None
        count = override if override is not None else len(dates)
        funded = sum(
            abs(t.amount_cents)
            for t in txs
            if start <= t.booking_date <= end
            and (c := classified.get(t.id))
            and c.budget_id == budget.id
            and c.kind == "FUNDED"
        )
        spent = sum(
            abs(t.amount_cents)
            for t in txs
            if start <= (t.operation_date or t.booking_date) <= end
            and (c := classified.get(t.id))
            and c.budget_id == budget.id
            and c.kind == "SPENT"
        )
        planned = count * budget.amount_cents
        budget_rows.append(
            {
                "id": budget.id,
                "name": budget.name,
                "amount_cents": budget.amount_cents,
                "frequency": budget.frequency,
                "anchor_date": budget.anchor_date.isoformat(),
                "count": count,
                "manual_count": override,
                "expected_cents": planned,
                "funded_cents": funded,
                "spent_cents": spent,
                "remaining_cents": max(0, planned - funded),
                "explanation": "Le reste à protéger diminue avec les virements de financement "
                "CHARGES → DÉPENSES. Les achats alimentent le consommé, "
                "sans être soustraits deux fois.",
            }
        )
    transactions = []
    for tx in txs:
        c = classified.get(tx.id)
        if start <= tx.booking_date <= end:
            transactions.append(
                {
                    "id": tx.id,
                    "account_id": tx.account_id,
                    "account_name": account_map[tx.account_id].name,
                    "booking_date": tx.booking_date.isoformat(),
                    "operation_date": tx.operation_date.isoformat() if tx.operation_date else None,
                    "amount_cents": tx.amount_cents,
                    "raw_label": tx.raw_label,
                    "kind": c.kind if c else None,
                    "charge_id": c.charge_id if c else None,
                    "budget_id": c.budget_id if c else None,
                }
            )
    unknown = [t for t in transactions if t["kind"] is None]
    adjustments = [
        {"id": a.id, "name": a.name, "amount_cents": a.amount_cents}
        for a in db.scalars(select(Adjustment).where(Adjustment.month == month))
    ]
    charges_total = sum(c["remaining_cents"] for c in charge_rows)
    budgets_total = sum(b["remaining_cents"] for b in budget_rows)
    adjustment_total = sum(a["amount_cents"] for a in adjustments)
    balance = charges_account.balance_cents if charges_account else 0
    return {
        "month": month,
        "today": today.isoformat(),
        "configured": bool(charges_account),
        "accounts": [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role,
                "balance_cents": a.balance_cents,
                "balance_date": a.balance_date.isoformat(),
            }
            for a in accounts
        ],
        "balance_cents": balance,
        "balance_date": charges_account.balance_date.isoformat() if charges_account else None,
        "charges": charge_rows,
        "budgets": budget_rows,
        "transactions": transactions,
        "adjustments": adjustments,
        "anomalies": anomalies,
        "unclassified_count": len(unknown),
        "charges_cents": charges_total,
        "budgets_cents": budgets_total,
        "adjustments_cents": adjustment_total,
        "safety_cents": safety,
        "treasury_cents": goal,
        "is_current_month": start <= today <= end,
        **totals(balance, charges_total, budgets_total, adjustment_total, safety, goal),
    }

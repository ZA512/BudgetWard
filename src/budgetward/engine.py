"""Pure recurrence calculations; all money is represented by integer cents."""

import calendar
from datetime import date, timedelta


def month_bounds(month: str) -> tuple[date, date]:
    start = date.fromisoformat(f"{month}-01")
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def occurrences(
    month: str,
    frequency: str,
    anchor: date,
    end_date: date | None = None,
    installment_count: int | None = None,
) -> list[date]:
    start, end = month_bounds(month)
    if frequency == "MANUAL":
        return []
    result = []
    if frequency in {"WEEKLY", "EVERY_2_WEEKS"}:
        step = 7 if frequency == "WEEKLY" else 14
        delta = max(0, (start - anchor).days)
        first = anchor + timedelta(days=((delta + step - 1) // step) * step)
        current = first
        while current <= end:
            if end_date is None or current <= end_date:
                result.append(current)
            current += timedelta(days=step)
        return result
    interval = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}[frequency]
    months = (start.year - anchor.year) * 12 + start.month - anchor.month
    if months < 0 or months % interval:
        return []
    occurrence = start.replace(day=min(anchor.day, end.day))
    if occurrence < anchor or (end_date and occurrence > end_date):
        return []
    if installment_count is not None and months // interval >= installment_count:
        return []
    return [occurrence]


def totals(balance: int, charges: int, budgets: int, adjustments: int, safety: int, goal: int):
    protected = max(0, charges + budgets + adjustments + safety + goal)
    difference = balance - protected
    return {
        "protected_cents": protected,
        "transferable_cents": max(0, difference),
        "deficit_cents": max(0, -difference),
    }

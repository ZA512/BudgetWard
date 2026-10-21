from datetime import date

import pytest

from budgetward.engine import occurrences, totals


def test_five_saturdays_and_next_month_four():
    anchor = date(2026, 10, 3)
    assert len(occurrences("2026-10", "WEEKLY", anchor)) == 5
    assert len(occurrences("2026-11", "WEEKLY", anchor)) == 4


def test_every_other_week_preserves_phase_across_months():
    anchor = date(2026, 10, 13)
    assert occurrences("2026-10", "EVERY_2_WEEKS", anchor) == [
        date(2026, 10, 13),
        date(2026, 10, 27),
    ]
    assert occurrences("2026-11", "EVERY_2_WEEKS", anchor) == [
        date(2026, 11, 10),
        date(2026, 11, 24),
    ]


def test_installments_end_and_end_of_month_is_clamped():
    anchor = date(2026, 11, 30)
    assert occurrences("2027-02", "MONTHLY", anchor, installment_count=4) == [date(2027, 2, 28)]
    assert occurrences("2027-03", "MONTHLY", anchor, installment_count=4) == []
    assert occurrences("2026-10", "MONTHLY", anchor) == []


def test_lifecycle_end_date():
    assert occurrences("2026-10", "WEEKLY", date(2026, 10, 3), date(2026, 10, 17)) == [
        date(2026, 10, 3),
        date(2026, 10, 10),
        date(2026, 10, 17),
    ]


@pytest.mark.parametrize(
    "frequency,month,count",
    [
        ("QUARTERLY", "2026-11", 0),
        ("QUARTERLY", "2027-01", 1),
        ("YEARLY", "2027-10", 1),
        ("YEARLY", "2027-09", 0),
        ("MANUAL", "2026-10", 0),
    ],
)
def test_other_frequencies(frequency, month, count):
    assert len(occurrences(month, frequency, date(2026, 10, 1))) == count


def test_prd_result_and_deficit_never_negative_transfer():
    assert totals(497000, 232000, 186500, 0, 10000, 15000) == {
        "protected_cents": 443500,
        "transferable_cents": 53500,
        "deficit_cents": 0,
    }
    assert totals(-10000, 10000, 0, 0, 0, 0)["deficit_cents"] == 20000
    assert totals(-10000, 10000, 0, 0, 0, 0)["transferable_cents"] == 0

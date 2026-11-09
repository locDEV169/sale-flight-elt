"""Lightweight checks for extract helpers."""

from datetime import date

from elt.extract import departure_months


def test_departure_months_horizon_three():
    months = departure_months(3, today=date(2026, 11, 9))
    assert months == ["2026-11", "2026-12", "2027-01"]


def test_departure_months_year_wrap():
    months = departure_months(2, today=date(2026, 12, 1))
    assert months == ["2026-12", "2027-01"]

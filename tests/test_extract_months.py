"""Lightweight checks for extract helpers."""

from datetime import date

from elt.extract import departure_months, sample_outbound_date


def test_departure_months_horizon_three():
    months = departure_months(3, today=date(2026, 11, 9))
    assert months == ["2026-11", "2026-12", "2027-01"]


def test_departure_months_year_wrap():
    months = departure_months(2, today=date(2026, 12, 1))
    assert months == ["2026-12", "2027-01"]


def test_sample_outbound_date_current_month_uses_tomorrow():
    assert sample_outbound_date("2026-11", today=date(2026, 11, 9)) == "2026-11-10"


def test_sample_outbound_date_current_month_end_clamps():
    assert sample_outbound_date("2026-11", today=date(2026, 11, 30)) == "2026-11-30"


def test_sample_outbound_date_future_month_uses_day_15():
    assert sample_outbound_date("2026-12", today=date(2026, 11, 9)) == "2026-12-15"

"""Lightweight checks for extract date helpers."""

from datetime import date

import pytest

from elt.extract import outbound_dates


def test_outbound_dates_today_through_plus_three():
    dates = outbound_dates(3, today=date(2026, 11, 9))
    assert dates == [
        "2026-11-09",
        "2026-11-10",
        "2026-11-11",
        "2026-11-12",
    ]


def test_outbound_dates_zero_is_today_only():
    assert outbound_dates(0, today=date(2026, 11, 9)) == ["2026-11-09"]


def test_outbound_dates_rejects_negative():
    with pytest.raises(ValueError):
        outbound_dates(-1, today=date(2026, 11, 9))

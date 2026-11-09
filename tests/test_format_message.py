"""Unit check for Telegram alert message formatting."""

from datetime import datetime, timezone

from elt.alert.telegram import format_message


def test_format_message_includes_drop_and_route():
    text = format_message(
        {
            "origin": "DAD",
            "destination": "SGN",
            "departure_month": "2026-11-10",
            "price": 900000,
            "baseline": 1200000,
            "drop_pct": 25.0,
            "currency": "VND",
            "airline": "Vietjet",
            "transfers": 0,
            "queried_at": datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc),
        },
        {("DAD", "SGN"): "Da Nang -> Ho Chi Minh City"},
    )
    assert "DAD -> SGN" in text
    assert "25.0%" in text
    assert "900000" in text
    assert "Vietjet" in text

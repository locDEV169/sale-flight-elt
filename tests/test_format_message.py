"""Unit check for Telegram alert message formatting."""

import json
from datetime import datetime, timezone

from elt.alert.telegram import format_message


def test_format_message_includes_flight_leg_details():
    flights = [
        {
            "departure_airport": {
                "name": "Da Nang International Airport",
                "id": "DAD",
                "time": "2026-11-10 08:00",
            },
            "arrival_airport": {
                "name": "Tan Son Nhat International Airport",
                "id": "SGN",
                "time": "2026-11-10 09:25",
            },
            "duration": 85,
            "airplane": "Airbus A321",
            "airline": "Vietjet",
            "travel_class": "Economy",
            "flight_number": "VJ 123",
        }
    ]
    text = format_message(
        {
            "origin": "DAD",
            "destination": "SGN",
            "departure_month": "2026-11-10",
            "price": 900000,
            "currency": "VND",
            "airline": "Vietjet",
            "transfers": 0,
            "total_duration": 85,
            "flights_json": json.dumps(flights),
            "queried_at": datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc),
        },
        {("DAD", "SGN"): "Da Nang -> Ho Chi Minh City"},
    )
    assert "Flight price alert" in text
    assert "DAD -> SGN" in text
    assert "900000" in text
    assert "VJ 123 · Airbus A321 · Economy" in text
    assert "DAD 08:00 → SGN 09:25 (85 min)" in text
    assert "Baseline" not in text


def test_format_message_multi_leg_and_fallback_without_flights_json():
    flights = [
        {
            "departure_airport": {"id": "DAD", "time": "2026-11-10 08:00"},
            "arrival_airport": {"id": "HAN", "time": "2026-11-10 09:30"},
            "duration": 90,
            "airplane": "A320",
            "travel_class": "Economy",
            "flight_number": "VN 1",
        },
        {
            "departure_airport": {"id": "HAN", "time": "2026-11-10 12:00"},
            "arrival_airport": {"id": "SGN", "time": "2026-11-10 14:00"},
            "duration": 120,
            "airplane": "A321",
            "travel_class": "Economy",
            "flight_number": "VN 2",
        },
    ]
    multi = format_message(
        {
            "origin": "DAD",
            "destination": "SGN",
            "departure_month": "2026-11-10",
            "price": 1_000_000,
            "currency": "VND",
            "transfers": 1,
            "total_duration": 360,
            "flights_json": flights,
            "queried_at": "2026-11-10T00:00:00+00:00",
        },
        {},
    )
    assert "VN 1" in multi
    assert "VN 2" in multi
    assert "Total duration: 360 min" in multi
    assert "Transfers: 1" in multi

    fallback = format_message(
        {
            "origin": "DAD",
            "destination": "SGN",
            "departure_month": "2026-11-10",
            "price": 900000,
            "currency": "VND",
            "airline": "Vietjet",
            "transfers": 0,
            "flights_json": None,
            "queried_at": "2026-11-10T00:00:00+00:00",
        },
        {},
    )
    assert "Airline: Vietjet" in fallback

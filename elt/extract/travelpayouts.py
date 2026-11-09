"""Extract flight prices from Travelpayouts API."""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_TIMEOUT_SEC = 30


def departure_months(horizon_months: int, today: date | None = None) -> list[str]:
    """Return YYYY-MM for current month + (horizon_months - 1) following months."""
    base = today or date.today()
    year, month = base.year, base.month
    out: list[str] = []
    for _ in range(horizon_months):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return out


def fetch_prices(
    *,
    token: str,
    origin: str,
    destination: str,
    departure_month: str,
    currency: str,
    market: str,
    api_base: str,
) -> tuple[dict[str, Any], int, str | None]:
    """
    Call prices_for_dates once.
    Returns (payload_or_empty, http_status, error_message).
    Retries once on 429 / 5xx / timeout.
    """
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": departure_month,
        "one_way": "true",
        "direct": "false",
        "currency": currency,
        "sorting": "price",
        "unique": "false",
        "limit": "30",
        "page": "1",
        "market": market,
    }
    headers = {"X-Access-Token": token}

    last_error: str | None = None
    last_status = 0
    for attempt in range(2):
        try:
            resp = requests.get(
                api_base,
                params=params,
                headers=headers,
                timeout=API_TIMEOUT_SEC,
            )
            last_status = resp.status_code
            if resp.status_code == 200:
                return resp.json(), 200, None
            if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                logger.warning(
                    "retryable status %s for %s-%s %s; sleep 5s",
                    resp.status_code,
                    origin,
                    destination,
                    departure_month,
                )
                time.sleep(5)
                continue
            last_error = resp.text[:500]
            return {}, last_status, last_error
        except requests.RequestException as exc:
            last_error = str(exc)
            last_status = 0
            if attempt == 0:
                logger.warning("request error %s; sleep 5s", exc)
                time.sleep(5)
                continue
            return {}, last_status, last_error

    return {}, last_status, last_error


def extract_all(
    *,
    token: str,
    routes: list[dict],
    currency: str,
    market: str,
    horizon_months: int,
    api_base: str,
    run_id: str,
    queried_at_iso: str,
) -> list[dict[str, Any]]:
    """Extract all route × month combinations into raw row dicts."""
    rows: list[dict[str, Any]] = []
    months = departure_months(horizon_months)
    for route in routes:
        origin = route["origin"]
        destination = route["destination"]
        for month in months:
            request_params = {
                "origin": origin,
                "destination": destination,
                "departure_at": month,
                "one_way": True,
                "direct": False,
                "currency": currency,
                "sorting": "price",
                "unique": False,
                "limit": 30,
                "page": 1,
                "market": market,
            }
            payload, status, error = fetch_prices(
                token=token,
                origin=origin,
                destination=destination,
                departure_month=month,
                currency=currency,
                market=market,
                api_base=api_base,
            )
            # Fallback market=ru once if vn returned empty data with 200
            if (
                status == 200
                and market == "vn"
                and isinstance(payload, dict)
                and not payload.get("data")
            ):
                logger.info(
                    "empty data for %s-%s %s with market=vn; retry market=ru",
                    origin,
                    destination,
                    month,
                )
                request_params["market"] = "ru"
                payload, status, error = fetch_prices(
                    token=token,
                    origin=origin,
                    destination=destination,
                    departure_month=month,
                    currency=currency,
                    market="ru",
                    api_base=api_base,
                )

            rows.append(
                {
                    "run_id": run_id,
                    "queried_at": queried_at_iso,
                    "origin": origin,
                    "destination": destination,
                    "departure_month": month,
                    "request_params": json.dumps(request_params, ensure_ascii=False),
                    "payload": json.dumps(payload, ensure_ascii=False)
                    if payload
                    else None,
                    "http_status": status,
                    "error": error,
                }
            )
            logger.info(
                "extracted %s-%s %s status=%s",
                origin,
                destination,
                month,
                status,
            )
    return rows

"""Extract flight prices from SerpAPI Google Flights."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from typing import Any

import serpapi

logger = logging.getLogger(__name__)


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


def sample_outbound_date(year_month: str, today: date | None = None) -> str:
    """
    Pick one YYYY-MM-DD per month for SerpAPI (needs a concrete date).
    Current month → tomorrow (clamped to month end); other months → day 15.
    """
    base = today or date.today()
    year_s, month_s = year_month.split("-", 1)
    year, month = int(year_s), int(month_s)

    if year == base.year and month == base.month:
        candidate = base + timedelta(days=1)
        if candidate.month != month:
            candidate = base
        return candidate.isoformat()

    return date(year, month, 15).isoformat()


def fetch_prices(
    *,
    api_key: str,
    query: dict[str, Any],
) -> tuple[dict[str, Any], int, str | None]:
    """
    Call SerpAPI google_flights once.
    Returns (payload_or_empty, http_status, error_message).
    Retries once on transient errors.
    """
    client = serpapi.Client(api_key=api_key)
    last_error: str | None = None
    last_status = 0

    for attempt in range(2):
        try:
            results = client.search(query)
            if not isinstance(results, dict):
                return {}, 0, f"unexpected result type: {type(results)!r}"

            # SerpAPI often embeds error info in the JSON body.
            if results.get("error"):
                last_error = str(results["error"])[:500]
                last_status = int(results.get("status") or 400)
                if attempt == 0 and last_status in (429, 500, 502, 503, 504):
                    logger.warning("retryable serpapi error %s; sleep 5s", last_error)
                    time.sleep(5)
                    continue
                return results, last_status, last_error

            return results, 200, None
        except Exception as exc:  # noqa: BLE001 — network/SDK surface is broad
            last_error = str(exc)[:500]
            last_status = 0
            if attempt == 0:
                logger.warning("serpapi request error %s; sleep 5s", exc)
                time.sleep(5)
                continue
            return {}, last_status, last_error

    return {}, last_status, last_error


def extract_all(
    *,
    api_key: str,
    routes: list[dict],
    query_defaults: dict[str, Any],
    horizon_months: int,
    run_id: str,
    queried_at_iso: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Extract all route × month combinations into raw row dicts."""
    rows: list[dict[str, Any]] = []
    months = departure_months(horizon_months, today=today)
    for route in routes:
        origin = route["origin"]
        destination = route["destination"]
        for month in months:
            outbound_date = sample_outbound_date(month, today=today)
            request_params = {
                **query_defaults,
                "departure_id": origin,
                "arrival_id": destination,
                "outbound_date": outbound_date,
            }
            payload, status, error = fetch_prices(
                api_key=api_key,
                query=request_params,
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
                "extracted %s-%s %s outbound=%s status=%s",
                origin,
                destination,
                month,
                outbound_date,
                status,
            )
    return rows

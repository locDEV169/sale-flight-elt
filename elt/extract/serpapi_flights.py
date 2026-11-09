"""Extract flight prices from SerpAPI Google Flights."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from typing import Any

import serpapi

logger = logging.getLogger(__name__)


def outbound_dates(horizon_days: int, today: date | None = None) -> list[str]:
    """
    Return YYYY-MM-DD from today through today+horizon_days (inclusive).
    Example: horizon_days=3 → 4 dates.
    """
    if horizon_days < 0:
        raise ValueError("horizon_days must be >= 0")
    base = today or date.today()
    return [(base + timedelta(days=i)).isoformat() for i in range(horizon_days + 1)]


def _as_payload_dict(results: Any) -> dict[str, Any] | None:
    """Normalize serpapi Client.search() output to a plain dict."""
    if isinstance(results, dict):
        return results
    as_dict = getattr(results, "as_dict", None)
    if callable(as_dict):
        data = as_dict()
        return data if isinstance(data, dict) else None
    return None


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
            payload = _as_payload_dict(results)
            if payload is None:
                return {}, 0, f"unexpected result type: {type(results)!r}"

            # SerpAPI often embeds error info in the JSON body.
            if payload.get("error"):
                last_error = str(payload["error"])[:500]
                last_status = int(payload.get("status") or 400)
                if attempt == 0 and last_status in (429, 500, 502, 503, 504):
                    logger.warning("retryable serpapi error %s; sleep 5s", last_error)
                    time.sleep(5)
                    continue
                return payload, last_status, last_error

            # Full response kept as-is (best_flights, other_flights, price_insights, …).
            return payload, 200, None
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
    horizon_days: int,
    run_id: str,
    queried_at_iso: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Extract all route × outbound-date combinations into raw row dicts."""
    rows: list[dict[str, Any]] = []
    dates = outbound_dates(horizon_days, today=today)
    for route in routes:
        origin = route["origin"]
        destination = route["destination"]
        for outbound_date in dates:
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
            # ponytail: reuse departure_month STRING column to store YYYY-MM-DD
            # so baseline key is per flight date without a schema migration.
            rows.append(
                {
                    "run_id": run_id,
                    "queried_at": queried_at_iso,
                    "origin": origin,
                    "destination": destination,
                    "departure_month": outbound_date,
                    "request_params": json.dumps(request_params, ensure_ascii=False),
                    "payload": json.dumps(payload, ensure_ascii=False)
                    if payload
                    else None,
                    "http_status": status,
                    "error": error,
                }
            )
            logger.info(
                "extracted %s-%s outbound=%s status=%s",
                origin,
                destination,
                outbound_date,
                status,
            )
    return rows

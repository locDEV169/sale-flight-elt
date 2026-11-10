"""Extract flight prices from SerpAPI Google Flights."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
from typing import Any

import serpapi

logger = logging.getLogger(__name__)

# SerpAPI HTTP errors often embed ?api_key=... in the exception URL.
_API_KEY_IN_URL = re.compile(r"(api_key=)([^&\s]+)", re.IGNORECASE)


def _redact_secrets(text: str) -> str:
    return _API_KEY_IN_URL.sub(r"\1***", text)


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


def _flight_counts(payload: dict[str, Any]) -> tuple[int, int]:
    best = payload.get("best_flights")
    other = payload.get("other_flights")
    n_best = len(best) if isinstance(best, list) else 0
    n_other = len(other) if isinstance(other, list) else 0
    return n_best, n_other


def _safe_query_for_log(query: dict[str, Any]) -> dict[str, Any]:
    """Copy query for logs; never include api_key."""
    return {k: v for k, v in query.items() if k != "api_key"}


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
    log_query = _safe_query_for_log(query)

    for attempt in range(2):
        try:
            results = client.search(query)
            payload = _as_payload_dict(results)
            if payload is None:
                msg = f"unexpected result type: {type(results)!r}"
                logger.error("serpapi bad result query=%s err=%s", log_query, msg)
                return {}, 0, msg

            # SerpAPI often embeds error info in the JSON body
            # (e.g. "Google Flights hasn't returned any results for this query.").
            if payload.get("error"):
                last_error = str(payload["error"])[:500]
                last_status = int(payload.get("status") or 400)
                meta = payload.get("search_metadata") if isinstance(
                    payload.get("search_metadata"), dict
                ) else {}
                n_best, n_other = _flight_counts(payload)
                logger.warning(
                    "serpapi body error attempt=%s status=%s err=%s "
                    "meta_status=%s n_best=%s n_other=%s query=%s",
                    attempt + 1,
                    last_status,
                    last_error,
                    meta.get("status"),
                    n_best,
                    n_other,
                    log_query,
                )
                if attempt == 0 and last_status in (429, 500, 502, 503, 504):
                    logger.warning("retryable serpapi error; sleep 5s")
                    time.sleep(5)
                    continue
                return payload, last_status, last_error

            n_best, n_other = _flight_counts(payload)
            # Full response kept as-is (best_flights, other_flights, price_insights, …).
            logger.info(
                "serpapi ok n_best=%s n_other=%s query=%s",
                n_best,
                n_other,
                log_query,
            )
            if n_best == 0 and n_other == 0:
                logger.warning(
                    "serpapi 200 but empty flights lists query=%s "
                    "(no snapshot/alert for this key)",
                    log_query,
                )
            return payload, 200, None
        except Exception as exc:  # noqa: BLE001 — network/SDK surface is broad
            last_error = _redact_secrets(str(exc)[:500])
            last_status = 0
            logger.warning(
                "serpapi request exception attempt=%s err=%s query=%s",
                attempt + 1,
                last_error,
                log_query,
            )
            if attempt == 0:
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
    logger.info(
        "extract start run_id=%s horizon_days=%s dates=%s routes=%s",
        run_id,
        horizon_days,
        dates,
        [(r.get("origin"), r.get("destination")) for r in routes],
    )
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
            n_best, n_other = _flight_counts(payload) if payload else (0, 0)
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
            if status == 200 and (n_best > 0 or n_other > 0):
                logger.info(
                    "extracted %s-%s outbound=%s status=%s n_best=%s n_other=%s",
                    origin,
                    destination,
                    outbound_date,
                    status,
                    n_best,
                    n_other,
                )
            else:
                logger.warning(
                    "extracted %s-%s outbound=%s status=%s n_best=%s n_other=%s "
                    "error=%s (no price snapshot/alert unless offers exist)",
                    origin,
                    destination,
                    outbound_date,
                    status,
                    n_best,
                    n_other,
                    error,
                )
    return rows

"""Send Telegram alerts and record them in BigQuery."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from google.cloud import bigquery

from elt.config import BQ_LOCATION

logger = logging.getLogger(__name__)


def format_message(
    candidate: dict[str, Any], route_labels: dict[tuple[str, str], str]
) -> str:
    origin = candidate["origin"]
    destination = candidate["destination"]
    label = route_labels.get((origin, destination), f"{origin} -> {destination}")
    queried_at = candidate.get("queried_at")
    if isinstance(queried_at, datetime):
        # Lazy ZoneInfo: Windows needs the `tzdata` package (see requirements.txt).
        queried_ict = queried_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).strftime(
            "%Y-%m-%d %H:%M %Z"
        )
    else:
        queried_ict = str(queried_at)

    drop_pct = candidate.get("drop_pct")
    drop_txt = f"{float(drop_pct):.1f}%" if drop_pct is not None else "n/a"
    lines = [
        "Flight price drop alert",
        f"Route: {label} ({origin} -> {destination})",
        f"Departure date: {candidate.get('departure_month')}",
        f"Current: {candidate.get('price')} {candidate.get('currency', 'VND')}",
        f"Baseline (MIN 7d): {candidate.get('baseline')} {candidate.get('currency', 'VND')}",
        f"Drop: {drop_txt}",
        f"Airline: {candidate.get('airline') or 'n/a'}",
        f"Transfers: {candidate.get('transfers') if candidate.get('transfers') is not None else 'n/a'}",
        f"Queried at: {queried_ict}",
    ]
    link = candidate.get("link")
    if link:
        lines.append(f"Link: {link}")
    return "\n".join(lines)


def send_telegram(*, bot_token: str, chat_id: str, text: str) -> str | None:
    if not bot_token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required to alert"
        )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    message_id = data.get("result", {}).get("message_id")
    return str(message_id) if message_id is not None else None


def record_alert(
    *,
    project_id: str,
    dataset: str,
    candidate: dict[str, Any],
    telegram_message_id: str | None,
    status: str = "sent",
    location: str = BQ_LOCATION,
) -> None:
    client = bigquery.Client(project=project_id, location=location)
    table_id = f"{project_id}.{dataset}.alerts"
    row = {
        "alert_id": str(uuid.uuid4()),
        "run_id": candidate["run_id"],
        "origin": candidate["origin"],
        "destination": candidate["destination"],
        "departure_month": candidate["departure_month"],
        "price": float(candidate["price"]),
        "baseline": float(candidate["baseline"]),
        "drop_pct": float(candidate["drop_pct"]),
        "currency": candidate.get("currency") or "VND",
        "airline": candidate.get("airline"),
        "transfers": candidate.get("transfers"),
        "link": candidate.get("link"),
        "channel": "telegram",
        "status": status,
        "sent_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
        "telegram_message_id": telegram_message_id,
    }
    errors = client.insert_rows_json(table_id, [row])
    if errors:
        raise RuntimeError(f"Failed to insert alert rows: {errors}")


def process_alerts(
    *,
    project_id: str,
    dataset: str,
    bot_token: str,
    chat_id: str,
    candidates: list[dict[str, Any]],
    routes: list[dict],
    location: str = BQ_LOCATION,
) -> int:
    labels = {(r["origin"], r["destination"]): r.get("label", "") for r in routes}
    sent = 0
    for candidate in candidates:
        text = format_message(candidate, labels)
        try:
            message_id = send_telegram(bot_token=bot_token, chat_id=chat_id, text=text)
            record_alert(
                project_id=project_id,
                dataset=dataset,
                candidate=candidate,
                telegram_message_id=message_id,
                status="sent",
                location=location,
            )
            sent += 1
            logger.info(
                "alert sent %s-%s %s drop=%.1f",
                candidate["origin"],
                candidate["destination"],
                candidate["departure_month"],
                float(candidate["drop_pct"]),
            )
        except Exception:
            logger.exception(
                "alert failed for %s-%s %s",
                candidate.get("origin"),
                candidate.get("destination"),
                candidate.get("departure_month"),
            )
    return sent

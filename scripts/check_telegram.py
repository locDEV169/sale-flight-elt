"""Smoke-check Telegram alert formatting + delivery (no BigQuery write)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elt.alert.telegram import format_message, send_telegram
from elt.config import get_settings, load_routes


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required "
            "(use a numeric chat/user id or channel id, not the bot @username)"
        )

    routes = load_routes(settings.routes_path)
    labels = {(r["origin"], r["destination"]): r.get("label", "") for r in routes}
    route = routes[0]
    candidate = {
        "origin": route["origin"],
        "destination": route["destination"],
        "departure_month": datetime.now(timezone.utc).date().isoformat(),
        "price": 900_000.0,
        "baseline": 1_200_000.0,
        "drop_pct": 25.0,
        "currency": "VND",
        "airline": "Vietjet",
        "transfers": 0,
        "queried_at": datetime.now(timezone.utc),
        "link": None,
    }
    text = "[TEST] " + format_message(candidate, labels)
    message_id = send_telegram(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        text=text,
    )
    print(
        f"OK: telegram message sent chat_id={settings.telegram_chat_id} "
        f"message_id={message_id}"
    )


if __name__ == "__main__":
    main()

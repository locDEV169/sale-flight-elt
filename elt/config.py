"""Load env + watched routes for the ELT worker."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    travelpayouts_token: str
    telegram_bot_token: str
    telegram_chat_id: str
    gcp_project_id: str
    bq_dataset: str
    gcs_bucket: str
    market: str
    currency: str
    horizon_months: int
    routes_path: Path
    sql_dir: Path
    staging_dir: Path
    api_base: str = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def get_settings() -> Settings:
    token = os.environ.get("TRAVELPAYOUTS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TRAVELPAYOUTS_TOKEN is required")

    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    dataset = os.environ.get("BQ_DATASET", "flight_elt").strip()
    bucket = os.environ.get("GCS_BUCKET", "").strip()
    if not project or not bucket:
        raise RuntimeError("GCP_PROJECT_ID and GCS_BUCKET are required")

    return Settings(
        travelpayouts_token=token,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        gcp_project_id=project,
        bq_dataset=dataset,
        gcs_bucket=bucket,
        market=os.environ.get("TRAVELPAYOUTS_MARKET", "vn").strip() or "vn",
        currency=os.environ.get("TRAVELPAYOUTS_CURRENCY", "usd").strip() or "usd",
        horizon_months=int(os.environ.get("HORIZON_MONTHS", "3")),
        routes_path=ROOT / "config" / "routes.json",
        sql_dir=ROOT / "sql",
        staging_dir=ROOT / "staging",
    )


def load_routes(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError(f"No routes found in {path}")
    for r in routes:
        if r.get("origin") != "DAD":
            raise RuntimeError(f"MVP requires origin=DAD, got {r}")
    return routes

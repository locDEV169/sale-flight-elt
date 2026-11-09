"""Load env + watched routes + SerpAPI query config for the ELT worker."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    serpapi_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    gcp_project_id: str
    bq_dataset: str
    gcs_bucket: str
    horizon_months: int
    routes_path: Path
    serpapi_query_path: Path
    sql_dir: Path
    staging_dir: Path


def get_settings() -> Settings:
    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY is required")

    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    dataset = os.environ.get("BQ_DATASET", "flight_elt").strip()
    bucket = os.environ.get("GCS_BUCKET", "").strip()
    if not project or not bucket:
        raise RuntimeError("GCP_PROJECT_ID and GCS_BUCKET are required")

    return Settings(
        serpapi_api_key=api_key,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        gcp_project_id=project,
        bq_dataset=dataset,
        gcs_bucket=bucket,
        horizon_months=int(os.environ.get("HORIZON_MONTHS", "3")),
        routes_path=ROOT / "config" / "routes.json",
        serpapi_query_path=ROOT / "config" / "serpapi_query.json",
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


def load_serpapi_query(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"Invalid SerpAPI query config in {path}")
    if data.get("engine") != "google_flights":
        raise RuntimeError(f"Expected engine=google_flights in {path}")
    return data

"""ELT pipeline orchestrator: Extract → Stage NDJSON → Load BQ → Transform SQL → Alert."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from elt.alert import process_alerts
from elt.config import get_settings, load_routes
from elt.extract import extract_all
from elt.load import load_raw_ndjson, upload_to_gcs, write_ndjson
from elt.transform import apply_ddl, fetch_alert_candidates, run_transform

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "staging" / ".pipeline.lock"


def _acquire_lock() -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        raise RuntimeError(f"Another pipeline run holds {LOCK_PATH}")
    LOCK_PATH.write_text(str(datetime.now(timezone.utc).isoformat()), encoding="utf-8")


def _release_lock() -> None:
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()


def run_once(*, init_schema: bool = False) -> None:
    settings = get_settings()
    routes = load_routes(settings.routes_path)
    run_id = str(uuid.uuid4())
    queried_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    _acquire_lock()
    try:
        if init_schema:
            apply_ddl(
                project_id=settings.gcp_project_id,
                dataset=settings.bq_dataset,
                ddl_path=settings.sql_dir / "bq_ddl.sql",
            )

        logger.info("run_id=%s starting extract", run_id)
        rows = extract_all(
            token=settings.travelpayouts_token,
            routes=routes,
            currency=settings.currency,
            market=settings.market,
            horizon_months=settings.horizon_months,
            api_base=settings.api_base,
            run_id=run_id,
            queried_at_iso=queried_at,
        )

        ndjson_path = settings.staging_dir / f"raw_{run_id}.ndjson"
        write_ndjson(rows, ndjson_path)

        object_name = f"raw/{queried_at[:10]}/raw_{run_id}.ndjson"
        gcs_uri = upload_to_gcs(
            bucket_name=settings.gcs_bucket,
            local_path=ndjson_path,
            object_name=object_name,
        )
        load_raw_ndjson(
            project_id=settings.gcp_project_id,
            dataset=settings.bq_dataset,
            gcs_uri=gcs_uri,
        )

        run_transform(
            project_id=settings.gcp_project_id,
            dataset=settings.bq_dataset,
            sql_path=settings.sql_dir / "bq_transform.sql",
            run_id=run_id,
        )

        candidates = fetch_alert_candidates(
            project_id=settings.gcp_project_id,
            dataset=settings.bq_dataset,
        )
        logger.info("alert candidates: %s", len(candidates))
        sent = process_alerts(
            project_id=settings.gcp_project_id,
            dataset=settings.bq_dataset,
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            candidates=candidates,
            routes=routes,
        )
        logger.info("run_id=%s done; alerts_sent=%s", run_id, sent)
    finally:
        _release_lock()

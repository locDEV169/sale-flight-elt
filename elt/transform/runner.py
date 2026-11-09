"""Run BigQuery Transform SQL after raw load."""

from __future__ import annotations

import logging
from pathlib import Path

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def _render_sql(sql_path: Path, dataset: str) -> str:
    text = sql_path.read_text(encoding="utf-8")
    return text.replace("__DATASET__", dataset)


def apply_ddl(*, project_id: str, dataset: str, ddl_path: Path) -> None:
    client = bigquery.Client(project=project_id)
    sql = _render_sql(ddl_path, dataset)
    job = client.query(sql)
    job.result()
    logger.info("applied DDL from %s", ddl_path)


def run_transform(
    *, project_id: str, dataset: str, sql_path: Path, run_id: str
) -> None:
    client = bigquery.Client(project=project_id)
    sql = _render_sql(sql_path, dataset)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]
    )
    job = client.query(sql, job_config=job_config)
    job.result()
    logger.info("transform finished for run_id=%s", run_id)


def fetch_alert_candidates(*, project_id: str, dataset: str) -> list[dict]:
    client = bigquery.Client(project=project_id)
    table = f"`{project_id}.{dataset}.alert_candidates`"
    rows = client.query(f"SELECT * FROM {table}").result()
    return [dict(row.items()) for row in rows]

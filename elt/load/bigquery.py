"""Load NDJSON to GCS then BigQuery (ELT Load step)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from google.cloud import bigquery, storage

from elt.config import BQ_LOCATION

logger = logging.getLogger(__name__)

RAW_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("queried_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("origin", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("destination", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("departure_month", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("request_params", "STRING"),
    bigquery.SchemaField("payload", "STRING"),
    bigquery.SchemaField("http_status", "INTEGER"),
    bigquery.SchemaField("error", "STRING"),
]


def check_bigquery_connection(
    *,
    project_id: str,
    dataset: str,
    location: str = BQ_LOCATION,
) -> dict[str, Any]:
    """Smoke-check BigQuery auth + dataset read access. Raises on failure."""
    client = bigquery.Client(project=project_id, location=location)
    rows = list(client.query("SELECT 1 AS ok").result())
    if not rows or int(rows[0]["ok"]) != 1:
        raise RuntimeError("BigQuery SELECT 1 returned unexpected result")
    ds = client.get_dataset(f"{project_id}.{dataset}")
    info = {
        "project": project_id,
        "dataset": dataset,
        "location": ds.location,
    }
    logger.info(
        "bigquery ok project=%s dataset=%s location=%s",
        info["project"],
        info["dataset"],
        info["location"],
    )
    return info


def upload_to_gcs(*, bucket_name: str, local_path: Path, object_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(local_path))
    uri = f"gs://{bucket_name}/{object_name}"
    logger.info("uploaded %s", uri)
    return uri


def load_raw_ndjson(
    *,
    project_id: str,
    dataset: str,
    gcs_uri: str,
    location: str = BQ_LOCATION,
) -> None:
    client = bigquery.Client(project=project_id, location=location)
    table_id = f"{project_id}.{dataset}.raw_flight_prices"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=RAW_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
    )
    job = client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    job.result()
    logger.info("loaded %s rows into %s", job.output_rows, table_id)

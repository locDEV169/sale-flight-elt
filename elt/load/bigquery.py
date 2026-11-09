"""Load NDJSON to GCS then BigQuery (ELT Load step)."""

from __future__ import annotations

import logging
from pathlib import Path

from google.cloud import bigquery, storage

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
) -> None:
    client = bigquery.Client(project=project_id)
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

"""Smoke-check BigQuery credentials + dataset access."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elt.config import get_settings
from elt.load.bigquery import check_bigquery_connection


def main() -> None:
    settings = get_settings()
    info = check_bigquery_connection(
        project_id=settings.gcp_project_id,
        dataset=settings.bq_dataset,
        location=settings.bq_location,
    )
    print(
        f"OK: project={info['project']} dataset={info['dataset']} "
        f"location={info['location']}"
    )


if __name__ == "__main__":
    main()

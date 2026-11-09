"""One-shot: apply BigQuery DDL from sql/bq_ddl.sql."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elt.config import get_settings
from elt.transform import apply_ddl


def main() -> None:
    settings = get_settings()
    apply_ddl(
        project_id=settings.gcp_project_id,
        dataset=settings.bq_dataset,
        ddl_path=settings.sql_dir / "bq_ddl.sql",
    )
    print(f"OK: schema applied to dataset {settings.bq_dataset}")


if __name__ == "__main__":
    main()

"""CLI for the ELT pipeline (used by root main.py and `python -m elt`)."""

from __future__ import annotations

import argparse
import logging

from elt.pipeline import run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="sale-flight BigQuery ELT pipeline")
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Apply sql/bq_ddl.sql before the run (first time setup)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_once(init_schema=args.init_schema)

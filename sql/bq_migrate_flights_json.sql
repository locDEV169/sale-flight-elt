-- Additive migrate for existing price_snapshots (safe to re-run).
-- Placeholder __DATASET__ is replaced by the worker / setup script.

ALTER TABLE `__DATASET__.price_snapshots`
  ADD COLUMN IF NOT EXISTS flights_json STRING;

ALTER TABLE `__DATASET__.price_snapshots`
  ADD COLUMN IF NOT EXISTS total_duration INT64;

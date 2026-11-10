-- BigQuery DDL for sale-flight ELT MVP
-- Replace PROJECT / DATASET via bq CLI or set in console before run.
-- Example:
--   bq query --use_legacy_sql=false < sql/bq_ddl.sql
-- Or substitute: flight_elt → your dataset id

-- Placeholder __DATASET__ is replaced by the worker / setup script.
CREATE SCHEMA IF NOT EXISTS `__DATASET__`
OPTIONS (location = 'asia-southeast1');

CREATE TABLE IF NOT EXISTS `__DATASET__.raw_flight_prices` (
  run_id STRING NOT NULL,
  queried_at TIMESTAMP NOT NULL,
  origin STRING NOT NULL,
  destination STRING NOT NULL,
  departure_month STRING NOT NULL,
  request_params STRING,
  payload STRING,
  http_status INT64,
  error STRING
)
PARTITION BY DATE(queried_at)
CLUSTER BY origin, destination, departure_month;

CREATE TABLE IF NOT EXISTS `__DATASET__.price_snapshots` (
  run_id STRING NOT NULL,
  queried_at TIMESTAMP NOT NULL,
  origin STRING NOT NULL,
  destination STRING NOT NULL,
  departure_month STRING NOT NULL,
  price FLOAT64 NOT NULL,
  currency STRING NOT NULL,
  airline STRING,
  transfers INT64,
  link STRING,
  flights_json STRING,
  total_duration INT64
)
PARTITION BY DATE(queried_at)
CLUSTER BY origin, destination, departure_month;

CREATE TABLE IF NOT EXISTS `__DATASET__.alerts` (
  alert_id STRING NOT NULL,
  run_id STRING NOT NULL,
  origin STRING NOT NULL,
  destination STRING NOT NULL,
  departure_month STRING NOT NULL,
  price FLOAT64 NOT NULL,
  baseline FLOAT64 NOT NULL,
  drop_pct FLOAT64 NOT NULL,
  currency STRING NOT NULL,
  airline STRING,
  transfers INT64,
  link STRING,
  channel STRING NOT NULL,
  status STRING NOT NULL,
  sent_at TIMESTAMP NOT NULL,
  telegram_message_id STRING
)
PARTITION BY DATE(sent_at)
CLUSTER BY origin, destination, departure_month;

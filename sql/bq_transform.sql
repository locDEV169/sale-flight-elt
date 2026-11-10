-- Transform step for one pipeline run (parameter: @run_id)
-- Placeholder __DATASET__ is replaced by the worker from BQ_DATASET.
-- Run after raw NDJSON has been loaded into raw_flight_prices.
-- Source payload: SerpAPI google_flights.
-- Offers: best_flights when non-empty; else other_flights (fallback).

-- 1) Build price_snapshots for this run from raw payloads
INSERT INTO `__DATASET__.price_snapshots`
  (run_id, queried_at, origin, destination, departure_month, price, currency,
   airline, transfers, link, flights_json, total_duration)
WITH raw_offers AS (
  SELECT
    r.run_id,
    r.queried_at,
    r.origin,
    r.destination,
    r.departure_month,
    JSON_VALUE(r.request_params, '$.currency') AS currency,
    offer
  FROM `__DATASET__.raw_flight_prices` AS r
  CROSS JOIN UNNEST(
    IF(
      ARRAY_LENGTH(IFNULL(JSON_EXTRACT_ARRAY(r.payload, '$.best_flights'), [])) > 0,
      IFNULL(JSON_EXTRACT_ARRAY(r.payload, '$.best_flights'), []),
      IFNULL(JSON_EXTRACT_ARRAY(r.payload, '$.other_flights'), [])
    )
  ) AS offer
  WHERE r.run_id = @run_id
    AND r.http_status = 200
    AND r.payload IS NOT NULL
),
picked AS (
  SELECT
    run_id,
    queried_at,
    origin,
    destination,
    departure_month,
    COALESCE(ANY_VALUE(currency), 'VND') AS currency,
    ARRAY_AGG(
      STRUCT(
        SAFE_CAST(JSON_VALUE(offer, '$.price') AS FLOAT64) AS price,
        JSON_VALUE(offer, '$.flights[0].airline') AS airline,
        GREATEST(
          ARRAY_LENGTH(IFNULL(JSON_EXTRACT_ARRAY(offer, '$.flights'), [])) - 1,
          0
        ) AS transfers,
        CAST(NULL AS STRING) AS link,
        -- Option B: keep winning offer's flights[] for Telegram formatting.
        JSON_EXTRACT(offer, '$.flights') AS flights_json,
        SAFE_CAST(JSON_VALUE(offer, '$.total_duration') AS INT64) AS total_duration
      )
      ORDER BY SAFE_CAST(JSON_VALUE(offer, '$.price') AS FLOAT64) ASC
      LIMIT 1
    )[OFFSET(0)] AS best
  FROM raw_offers
  WHERE SAFE_CAST(JSON_VALUE(offer, '$.price') AS FLOAT64) IS NOT NULL
  GROUP BY run_id, queried_at, origin, destination, departure_month
)
SELECT
  run_id,
  queried_at,
  origin,
  destination,
  departure_month,
  best.price,
  currency,
  best.airline,
  best.transfers,
  best.link,
  best.flights_json,
  best.total_duration
FROM picked
WHERE best.price IS NOT NULL;

-- 2) alert_candidates: every snapshot this run, minus anti-spam 24h
-- (no warm-up ≥3, no drop_pct > 20)
CREATE OR REPLACE TABLE `__DATASET__.alert_candidates` AS
WITH current_snap AS (
  SELECT *
  FROM `__DATASET__.price_snapshots`
  WHERE run_id = @run_id
),
recent_alerts AS (
  SELECT
    origin,
    destination,
    departure_month,
    MAX(sent_at) AS last_sent_at
  FROM `__DATASET__.alerts`
  WHERE status = 'sent'
  GROUP BY origin, destination, departure_month
)
SELECT
  c.run_id,
  c.origin,
  c.destination,
  c.departure_month,
  c.queried_at,
  c.price,
  CAST(NULL AS FLOAT64) AS baseline,
  CAST(NULL AS FLOAT64) AS drop_pct,
  c.currency,
  c.airline,
  c.transfers,
  c.link,
  c.flights_json,
  c.total_duration,
  0 AS prior_count_7d
FROM current_snap AS c
LEFT JOIN recent_alerts AS a
  ON a.origin = c.origin
 AND a.destination = c.destination
 AND a.departure_month = c.departure_month
-- WHERE a.last_sent_at IS NULL
--    OR a.last_sent_at < TIMESTAMP_SUB(c.queried_at, INTERVAL 24 HOUR);

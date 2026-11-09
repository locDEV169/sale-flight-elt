-- Transform step for one pipeline run (parameter: @run_id)
-- Placeholder __DATASET__ is replaced by the worker from BQ_DATASET.
-- Run after raw NDJSON has been loaded into raw_flight_prices.

-- 1) Build price_snapshots for this run from raw payloads
INSERT INTO `__DATASET__.price_snapshots`
  (run_id, queried_at, origin, destination, departure_month, price, currency, airline, transfers, link)
WITH raw_offers AS (
  SELECT
    r.run_id,
    r.queried_at,
    r.origin,
    r.destination,
    r.departure_month,
    offer
  FROM `__DATASET__.raw_flight_prices` AS r
  CROSS JOIN UNNEST(
    IFNULL(JSON_EXTRACT_ARRAY(r.payload, '$.data'), [])
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
    ARRAY_AGG(
      STRUCT(
        SAFE_CAST(JSON_VALUE(offer, '$.price') AS FLOAT64) AS price,
        JSON_VALUE(offer, '$.airline') AS airline,
        SAFE_CAST(JSON_VALUE(offer, '$.transfers') AS INT64) AS transfers,
        JSON_VALUE(offer, '$.link') AS link
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
  'usd' AS currency,
  best.airline,
  best.transfers,
  best.link
FROM picked
WHERE best.price IS NOT NULL;

-- 2) Materialize alert_candidates for this run (warm-up, drop > 20%, anti-spam 24h)
CREATE OR REPLACE TABLE `__DATASET__.alert_candidates` AS
WITH current_snap AS (
  SELECT *
  FROM `__DATASET__.price_snapshots`
  WHERE run_id = @run_id
),
history AS (
  SELECT
    c.origin,
    c.destination,
    c.departure_month,
    c.run_id AS current_run_id,
    c.queried_at AS current_queried_at,
    c.price AS current_price,
    c.currency,
    c.airline,
    c.transfers,
    c.link,
    COUNTIF(
      p.run_id IS NOT NULL
      AND p.queried_at < c.queried_at
      AND p.queried_at >= TIMESTAMP_SUB(c.queried_at, INTERVAL 7 DAY)
    ) AS prior_count_7d,
    MIN(
      IF(
        p.run_id IS NOT NULL
        AND p.queried_at < c.queried_at
        AND p.queried_at >= TIMESTAMP_SUB(c.queried_at, INTERVAL 7 DAY),
        p.price,
        NULL
      )
    ) AS baseline
  FROM current_snap AS c
  LEFT JOIN `__DATASET__.price_snapshots` AS p
    ON p.origin = c.origin
   AND p.destination = c.destination
   AND p.departure_month = c.departure_month
  GROUP BY
    c.origin, c.destination, c.departure_month, c.run_id, c.queried_at,
    c.price, c.currency, c.airline, c.transfers, c.link
),
scored AS (
  SELECT
    *,
    SAFE_DIVIDE(baseline - current_price, baseline) * 100 AS drop_pct
  FROM history
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
  s.current_run_id AS run_id,
  s.origin,
  s.destination,
  s.departure_month,
  s.current_queried_at AS queried_at,
  s.current_price AS price,
  s.baseline,
  s.drop_pct,
  s.currency,
  s.airline,
  s.transfers,
  s.link,
  s.prior_count_7d
FROM scored AS s
LEFT JOIN recent_alerts AS a
  ON a.origin = s.origin
 AND a.destination = s.destination
 AND a.departure_month = s.departure_month
WHERE s.prior_count_7d >= 3
  AND s.baseline IS NOT NULL
  AND s.baseline > 0
  AND s.drop_pct > 20
  AND (
    a.last_sent_at IS NULL
    OR a.last_sent_at < TIMESTAMP_SUB(s.current_queried_at, INTERVAL 24 HOUR)
  );

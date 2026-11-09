# sale-flight — Flight Price Tracker (ELT + BigQuery)

Pipeline **ELT** theo dõi giá vé Google Flights qua **SerpAPI**, Load raw vào **Google BigQuery**, Transform bằng SQL, cảnh báo **Telegram** khi giảm sâu.

Chi tiết nghiệp vụ: [`docs/MVP_SPEC.md`](docs/MVP_SPEC.md).

## Kiến trúc (ELT, không phải ETL cổ điển)

```text
Cron (ICT 00/05/10/15/20)
  → Extract SerpAPI Google Flights (DAD → SGN × hôm nay..+HORIZON_DAYS)
  → Stage NDJSON (không CSV — payload nested)
  → Load GCS → BigQuery raw_flight_prices
  → Transform SQL (snapshots + alert_candidates)
  → Alert Telegram → ghi alerts
```

Mặc định `HORIZON_DAYS=0` → **1** search/run (chỉ `today`), chặng **DAD → SGN**. Tăng số ngày khi cần.

## Vì sao NDJSON, không CSV?

Raw response có `best_flights[]` lồng nhau. CSV dễ mất cấu trúc. MVP dùng **NDJSON → GCS → BigQuery Load Job**.

## Setup nhanh

### 1. GCP

1. Tạo GCP project + bật BigQuery & Cloud Storage API  
2. Tạo GCS bucket  
3. Tạo Service Account với quyền tối thiểu: BigQuery Data Editor, BigQuery Job User, Storage Object Admin  
4. Tải key JSON vào `secrets/gcp-sa.json` (thư mục đã gitignore)

### 2. Local

```bash
python -m venv .venv
# Windows Git Bash:
source .venv/Scripts/activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Điền SERPAPI_API_KEY, Telegram, GCP_*
```

Query params SerpAPI nằm ở [`config/serpapi_query.json`](config/serpapi_query.json) (engine, type, currency, …).

### 3. Smoke-check BigQuery

```bash
python scripts/check_bq.py
# OK: project=... dataset=flight_elt location=asia-southeast1
```

### 3b. Smoke-check Telegram (fake alert, không ghi BQ)

```bash
python scripts/check_telegram.py
# OK: telegram message sent chat_id=... message_id=...
```

`TELEGRAM_CHAT_ID` phải là user/group/channel id nhận tin (số), không dùng `@username` của bot.

### 4. Schema BigQuery (một lần)

```bash
python scripts/init_bq_schema.py
```

### 5. Chạy 1 cycle

```bash
python main.py
# hoặc lần đầu kèm DDL:
python main.py --init-schema
# alias:
# python -m elt --init-schema
```

### 6. Cron trên VPS

Xem [`crontab`](crontab) — `TZ=Asia/Ho_Chi_Minh`, 5 mốc/ngày.

## Routes MVP

| Origin | Destination |
|--------|-------------|
| DAD | SGN |

## Rule alert (tóm tắt)

- `current = min(price)` trong `best_flights`  
- `baseline = MIN` snapshot 7 ngày trước (cùng origin/destination/**ngày bay**)  
- Alert nếu warm-up ≥ 3 snapshots, `drop_pct > 20`, chưa alert cùng key trong 24h  

## Test nhẹ

```bash
python -m pytest tests/ -q
```

## Cấu trúc

```text
main.py
elt/
  extract/serpapi_flights.py    # E — SerpAPI Google Flights
  load/stage.py                 # NDJSON staging
  load/bigquery.py              # L — GCS + BQ load
  transform/runner.py           # T — run sql/
  alert/telegram.py             # notify
  pipeline.py / cli.py / config.py
config/routes.json
config/serpapi_query.json
sql/bq_ddl.sql
sql/bq_transform.sql
scripts/init_bq_schema.py
crontab                         # orchestration MVP (not Airflow)
```

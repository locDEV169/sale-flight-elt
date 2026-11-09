# sale-flight — Flight Price Tracker (ELT + BigQuery)

Pipeline **ELT** theo dõi giá vé cached từ Travelpayouts, Load raw vào **Google BigQuery**, Transform bằng SQL, cảnh báo **Telegram** khi giảm sâu.

Chi tiết nghiệp vụ: [`docs/MVP_SPEC.md`](docs/MVP_SPEC.md).

## Kiến trúc (ELT, không phải ETL cổ điển)

```text
Cron (ICT 00/05/10/15/20)
  → Extract Travelpayouts (DAD → HAN/SGN/BKK/SIN/PQC × 3 tháng)
  → Stage NDJSON (không CSV — payload nested)
  → Load GCS → BigQuery raw_flight_prices
  → Transform SQL (snapshots + alert_candidates)
  → Alert Telegram → ghi alerts
```

Giá Travelpayouts là **cached (~48h)**, không phải giá booking realtime.

## Vì sao NDJSON, không CSV?

Raw response có `data[]` lồng nhau. CSV dễ mất cấu trúc. MVP dùng **NDJSON → GCS → BigQuery Load Job**.

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
# Điền token Travelpayouts, Telegram, GCP_*
```

### 3. Schema BigQuery (một lần)

```bash
python scripts/init_bq_schema.py
```

### 4. Chạy 1 cycle

```bash
python main.py
# hoặc lần đầu kèm DDL:
python main.py --init-schema
# alias:
# python -m elt --init-schema
```

### 5. Cron trên VPS

Xem [`crontab`](crontab) — `TZ=Asia/Ho_Chi_Minh`, 5 mốc/ngày.

## Routes MVP

| Origin | Destination |
|--------|-------------|
| DAD | HAN |
| DAD | SGN |
| DAD | BKK |
| DAD | SIN |
| DAD | PQC |

## Rule alert (tóm tắt)

- `current = min(price)` trong response  
- `baseline = MIN` snapshot 7 ngày trước (cùng origin/destination/month)  
- Alert nếu warm-up ≥ 3 snapshots, `drop_pct > 20`, chưa alert cùng key trong 24h  

## Test nhẹ

```bash
python -m pytest tests/ -q
```

## Cấu trúc

```text
main.py
elt/
  extract/travelpayouts.py      # E — source connector
  load/stage.py                 # NDJSON staging
  load/bigquery.py              # L — GCS + BQ load
  transform/runner.py           # T — run sql/
  alert/telegram.py             # notify
  pipeline.py / cli.py / config.py
config/routes.json
sql/bq_ddl.sql
sql/bq_transform.sql
scripts/init_bq_schema.py
crontab                         # orchestration MVP (not Airflow)
```

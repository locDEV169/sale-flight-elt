# MVP Spec — Flight Price Tracker & Alert (ELT)

> **Repo:** `sale-flight`  
> **Trạng thái:** Đặc tả khóa cho MVP  
> **Kiến trúc:** **ELT** — Extract → Load raw (BigQuery) → Transform SQL → Alert  
> **Nhãn:** `[FACT]` = đề bài / docs API · `[MVP DECISION]` = quyết định chấp nhận cho MVP

---

## 1. Mục tiêu

Tự động quét giá vé máy bay (cached) theo lịch cố định trong ngày, **Load raw vào Google BigQuery**, Transform bằng SQL, và gửi cảnh báo Telegram khi phát hiện giảm giá sâu trên các chặng **xuất phát từ Đà Nẵng (`DAD`)**.

Đáp ứng yêu cầu đồ án `[FACT]`:

- Chạy tự động **5 lần/ngày**, mỗi lần cách **5 giờ**
- Tự setup / chạy trên VPS
- Pipeline dữ liệu thực tế (**ELT** trên BigQuery)

---

## 2. Phạm vi MVP

### Trong phạm vi

- Python batch pipeline (Extract + Stage + Load + Alert)
- Cron trên VPS
- Google BigQuery (warehouse) + GCS (staging NDJSON)
- Travelpayouts `prices_for_dates`
- Telegram Bot (1 chat)
- 5 chặng cố định, origin = `DAD`
- Transform bằng **SQL trên BigQuery**

### Ngoài phạm vi (không làm trong MVP)

- PostgreSQL / dual-write Postgres + BigQuery
- CSV trên đường nóng Extract → Load raw (xem mục 7)
- Web UI / dashboard
- Celery / Redis / Prefect / Airflow
- Discord
- Multi-user / nhiều chat
- Round-trip / `return_at`
- ML dự đoán giá
- Cloud Scheduler / Cloud Run (có thể sau)
- Dynamic route management UI

---

## 3. Actors

| Actor | Vai trò |
|---|---|
| Cron (`Asia/Ho_Chi_Minh`) | Kích hoạt pipeline theo lịch |
| ELT Worker (Python) | Extract → NDJSON → Load BQ → chạy SQL Transform → Alert |
| Travelpayouts API | Nguồn giá cached |
| GCS | Staging file NDJSON trước Load Job |
| BigQuery | Warehouse: raw + snapshots + alerts |
| Telegram Bot | Kênh cảnh báo |
| GCP Service Account | Auth load/query BigQuery + GCS |
| Student Operator | Deploy VPS, secrets, xem BQ Console / log |

---

## 4. Watched routes `[MVP DECISION]`

**Origin luôn là `DAD`.**

| # | Origin | Destination | Label |
|---|---|---|---|
| 1 | `DAD` | `HAN` | Đà Nẵng → Hà Nội |
| 2 | `DAD` | `SGN` | Đà Nẵng → TP.HCM |
| 3 | `DAD` | `BKK` | Đà Nẵng → Bangkok |
| 4 | `DAD` | `SIN` | Đà Nẵng → Singapore |
| 5 | `DAD` | `PQC` | Đà Nẵng → Phú Quốc |

---

## 5. Lịch chạy `[FACT]` + `[MVP DECISION]`

| Mục | Giá trị |
|---|---|
| Timezone | `Asia/Ho_Chi_Minh` |
| Các mốc | `00:00`, `05:00`, `10:00`, `15:00`, `20:00` |
| Cron | `0 0,5,10,15,20 * * *` (kèm `TZ=Asia/Ho_Chi_Minh`) |

---

## 6. Extract — Travelpayouts API

### Endpoint `[FACT]`

```text
GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates
```

### Bản chất dữ liệu `[FACT]`

- Giá vé rẻ theo tìm kiếm của users Aviasales (cached, khoảng **48 giờ**)
- **Không** phải giá booking realtime
- Rate limit tham chiếu: **~600 req/phút**; vượt → HTTP **429**

### Auth `[FACT]`

- Header `X-Access-Token: <TOKEN>` (ưu tiên), hoặc query `token=`

### Params MVP `[MVP DECISION]`

| Param | Value | Ghi chú |
|---|---|---|
| `origin` | `DAD` | Cố định |
| `destination` | theo bảng routes | |
| `departure_at` | `YYYY-MM` | Horizon: **tháng hiện tại + 2 tháng tới** |
| `one_way` | `true` | |
| `return_at` | *(omit)* | Không dùng round-trip |
| `direct` | `false` | Cho phép nối chuyến |
| `currency` | `usd` | **Không dùng `cy`** |
| `sorting` | `price` | |
| `unique` | `false` | |
| `limit` | `30` | |
| `page` | `1` | |
| `market` | `vn` | Nếu lỗi/empty kéo dài → fallback `ru` + log |

### Volume mỗi run

`5 routes × 3 months = 15` HTTP calls / run  
`× 5 runs/ngày = 75` calls/ngày → an toàn so với 600/phút.

### API Discovery

| Bắt buộc MVP | Optional / sau MVP |
|---|---|
| `/aviasales/v3/prices_for_dates` + token + rate limit docs | Airports/cities dictionaries, month/week matrix, calendar, special offers, Discord, deep-link builder |

---

## 7. Load (raw) — NDJSON → GCS → BigQuery

### Flow Load `[MVP DECISION]`

1. Worker ghi **NDJSON** local (1 dòng = 1 API call + metadata + payload nested)
2. Upload lên **GCS**
3. **BigQuery Load Job** vào bảng `raw_flight_prices` (append-only)

### Vì sao không CSV cho raw?

| Format | Raw nested `data[]` | Kết luận MVP |
|---|---|---|
| CSV | Không fit — mất nested / escape lỗi | **Không dùng** trên đường nóng |
| NDJSON | 1 JSON/dòng, `bq load` tự nhiên | **Chọn** |
| `insert_rows_json` | Fit nhưng kém rõ “Load job” khi bảo vệ ELT | Không chọn cho MVP |

CSV chỉ hợp export báo cáo phẳng sau này — **không** nằm giữa Extract và Load raw.

### Cột raw tối thiểu

- `run_id` (STRING)
- `queried_at` (TIMESTAMP, lưu UTC; hiển thị ICT khi alert)
- `origin`, `destination`, `departure_month` (STRING)
- `request_params` (STRING / JSON)
- `payload` (STRING / JSON — giữ nguyên response)
- `http_status` (INT64)
- `error` (STRING, nullable)

DDL: `sql/bq_ddl.sql`.

---

## 8. Transform & Alert rules `[MVP DECISION]`

Transform chạy bằng **SQL trên BigQuery** (`sql/bq_transform.sql`) sau khi raw đã land.

### Giá đại diện của một query

```text
current = min(price) trong response.data
```

Nếu `data` rỗng → không tạo snapshot giá; không alert cho key đó.

### Khóa so sánh (baseline key)

```text
(origin, destination, departure_month)
```

Với MVP: `origin` luôn `DAD`.

### Baseline

```text
baseline = MIN(price) của các price_snapshots trước đó
           trong cửa sổ 7×24 giờ
           cùng baseline key
           KHÔNG gồm run hiện tại
```

### Công thức giảm giá

```text
drop_pct = (baseline - current) / baseline * 100
```

### Điều kiện gửi alert

Gửi Telegram **khi và chỉ khi** tất cả đúng:

1. Số snapshot lịch sử hợp lệ trong 7 ngày **≥ 3** (warm-up)
2. `drop_pct > 20`
3. Chưa có alert **thành công** cho cùng baseline key trong **24 giờ** (anti-spam)

SQL tạo/ghi `price_snapshots` và view/table `alert_candidates`.  
Python đọc `alert_candidates` → gửi Telegram → insert `alerts`.

### Hành vi warm-up / empty / lỗi

| Tình huống | Hành vi |
|---|---|
| `< 3` snapshot / 7 ngày | Load raw (+ snapshot nếu có giá); **không alert** |
| `data: []` | Raw OK; skip snapshot/alert |
| HTTP 429 | Log; retry 1 lần sau ~5s; không chặn route khác |
| 401/403 / timeout sau retry | Ghi lỗi; tiếp tục route khác |
| Load BQ fail | Không Transform/Alert cho run đó; log rõ |
| Overlap 2 job | Một runner (file lock đơn giản) |

---

## 9. Kênh cảnh báo

- **Telegram only** `[MVP DECISION]`
- Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### Nội dung message tối thiểu

- Route label + IATA (`DAD → HAN`)
- `departure_month`
- `current_price` (USD)
- `baseline` (USD)
- `drop_pct`
- `airline`, `transfers` (nếu có)
- `queried_at` (ICT)
- `link` (nếu API trả)

---

## 10. BigQuery schema tối thiểu

Dataset: cấu hình qua `BQ_DATASET` (vd. `flight_elt`).

| Table / view | Vai trò |
|---|---|
| `raw_flight_prices` | Append-only raw (sau Load Job) |
| `price_snapshots` | Curated `min(price)` theo run + key |
| `alert_candidates` | Kết quả Transform (đủ điều kiện alert, chưa gửi) |
| `alerts` | Lịch sử gửi Telegram |

`watched_routes`: hardcode `config/routes.json` (không bắt buộc bảng BQ).

Chi tiết: `sql/bq_ddl.sql`, `sql/bq_transform.sql`.

---

## 11. Stack & triển khai

| Thành phần | Lựa chọn MVP |
|---|---|
| Language | Python |
| Scheduler | Cron trên VPS |
| Staging | NDJSON + GCS |
| Warehouse | Google BigQuery |
| Transform | BigQuery SQL |
| Notify | Telegram Bot |
| Host | VPS (Ubuntu / cloud free-tier) |
| Auth GCP | Service Account JSON |

Secrets qua `.env` (không commit token / SA key):

- `TRAVELPAYOUTS_TOKEN`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `GCP_PROJECT_ID`, `BQ_DATASET`, `GCS_BUCKET`
- `GOOGLE_APPLICATION_CREDENTIALS` (path tới SA JSON)

---

## 12. Smoke test ngày 1

```http
GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates
  ?origin=DAD
  &destination=HAN
  &departure_at=2026-11
  &one_way=true
  &direct=false
  &currency=usd
  &sorting=price
  &unique=false
  &limit=30
  &page=1
  &market=vn
Header: X-Access-Token: <TOKEN>
```

Checklist:

1. `success: true` và có `data[].price`
2. Xác nhận đang dùng `currency` (không `cy`)
3. Thử lần lượt `SGN`, `BKK`, `SIN`, `PQC`
4. Nếu `market=vn` kém → thử `market=ru` và ghi nhận
5. Chạy 1 cycle pipeline: raw xuất hiện trên BQ **trước** khi Transform

---

## 13. Acceptance Criteria

1. **Schedule:** Pipeline chạy đúng 5 mốc ICT mỗi ngày.
2. **Origin:** Mọi watched request có `origin=DAD` và đúng 5 destination đã khóa.
3. **ELT raw-first:** Mỗi call được Load vào BigQuery `raw_flight_prices` (NDJSON load) **trước** Transform.
4. **Snapshot:** Khi có giá, SQL ghi `min(price)` vào `price_snapshots`.
5. **Alert:** Đủ warm-up ≥3 và `drop_pct > 20` → Telegram đủ field; ghi `alerts`.
6. **Anti-spam:** Không gửi lại cùng key trong 24h.
7. **Warm-up:** `<3` snapshot → không alert.
8. **API hygiene:** Path có `/aviasales/`; param tiền tệ là `currency=usd`.
9. **No CSV on hot path:** Staging raw là NDJSON, không CSV.
10. **Deploy:** Chạy trên VPS bằng Cron + SA; secret không nằm trong git.
11. **Narrative:** Bảo vệ gọi đúng **ELT** + BigQuery; nêu giới hạn cached ~48h.

---

## 14. Implementation checklist

- [x] `docs/MVP_SPEC.md` (BigQuery ELT)
- [ ] Smoke test API với token thật (`DAD-HAN` trước)
- [x] Tạo DDL/SQL BQ (`sql/bq_ddl.sql`, `sql/bq_transform.sql`)
- [x] `config/routes.json` (5 chặng DAD-*)
- [x] Worker: extract → stage NDJSON → load → transform SQL → alert
- [x] Cron template 5 slots + TZ (`crontab`)
- [x] `.env.example` + `.gitignore` (SA key)
- [ ] Deploy VPS + thử 1 run tay (cần GCP + token thật)
- [x] README: cách chạy, ELT, hạn chế cached data

---

## 15. Rủi ro đã biết

| Risk | Mitigation |
|---|---|
| Example docs dùng `cy` | MVP bắt buộc `currency=usd` |
| Giá cached ≠ giá mua | Nêu rõ trong báo cáo |
| CSV làm mất nested JSON | Chỉ NDJSON cho raw |
| SA key lộ | `.gitignore`; không commit |
| Một số chặng data mỏng | Smoke test; đổi destination sau nếu cần |
| Warm-up làm demo chưa alert | Seed / chạy ≥3 chu kỳ |

---

## 16. Changelog quyết định khóa

| Quyết định | Giá trị |
|---|---|
| Origin | Luôn `DAD` |
| Destinations | `HAN`, `SGN`, `BKK`, `SIN`, `PQC` |
| Baseline | `MIN` 7 ngày (không dùng AVG) |
| Ngưỡng | `drop_pct > 20` |
| Warm-up | ≥ 3 snapshots |
| Anti-spam | 24 giờ / baseline key |
| Channel | Telegram only |
| Currency param | `currency=usd` (không `cy`) |
| Horizon | Tháng hiện tại + 2 tháng |
| Architecture | **ELT** |
| Warehouse | **BigQuery** (thay PostgreSQL) |
| Staging | **NDJSON → GCS → Load Job** (không CSV raw) |
| Transform | **SQL trên BigQuery** |

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
- SerpAPI `google_flights`
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
| SerpAPI Google Flights | Nguồn giá (Google Flights via SerpAPI) |
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

## 6. Extract — SerpAPI Google Flights

### Client `[MVP DECISION]`

```python
import serpapi

client = serpapi.Client(api_key=SERPAPI_API_KEY)
results = client.search({...})
best_flights = results["best_flights"]
```

### Bản chất dữ liệu `[MVP DECISION]`

- Giá từ Google Flights qua SerpAPI
- SerpAPI cần `outbound_date` dạng **`YYYY-MM-DD`** (không nhận tháng)
- MVP lấy **1 ngày mẫu / tháng** để giữ volume và key theo ngày bay mẫu

### Auth `[MVP DECISION]`

- Env: `SERPAPI_API_KEY`
- Query params cố định: `config/serpapi_query.json`

### Params MVP `[MVP DECISION]`

| Param | Value | Ghi chú |
|---|---|---|
| `engine` | `google_flights` | config |
| `type` | `2` | one-way (config) |
| `currency` | `VND` | config |
| `hl` / `gl` | `vi` / `vn` | config |
| `departure_id` | `DAD` | từ routes |
| `arrival_id` | theo bảng routes | |
| `outbound_date` | `YYYY-MM-DD` | sample: tháng hiện tại → ngày mai; tháng khác → ngày 15 |

Horizon vẫn: **tháng hiện tại + 2 tháng tới** (`HORIZON_MONTHS=3`).  
Baseline key vẫn: `(origin, destination, departure_month)`.

### Volume mỗi run

`5 routes × 3 months = 15` SerpAPI searches / run  
`× 5 runs/ngày = 75` searches/ngày — theo dõi quota/billing SerpAPI.

### API Discovery

| Bắt buộc MVP | Optional / sau MVP |
|---|---|
| SerpAPI `google_flights` + `best_flights` | Nhiều ngày/tháng, `other_flights`, deep-link booking |

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
current = min(price) trong response.best_flights
          nếu best_flights rỗng/thiếu → min(price) trong other_flights
```

Nếu cả `best_flights` và `other_flights` rỗng / thiếu → không tạo snapshot giá; không alert cho key đó.

### Khóa so sánh (baseline key)

```text
(origin, destination, departure_month)
```

Với MVP: `origin` luôn `DAD`.

### Điều kiện gửi alert

Gửi Telegram **khi và chỉ khi** tất cả đúng:

1. Run hiện tại có `price_snapshots` (đã lấy được `min(price)` từ `best_flights`, fallback `other_flights`)
2. Chưa có alert **thành công** cho cùng baseline key trong **24 giờ** (anti-spam)

SQL tạo/ghi `price_snapshots` (kèm `flights_json`, `total_duration` của offer thắng) và table `alert_candidates`.  
Python đọc `alert_candidates` → format chi tiết chuyến bay → gửi Telegram → insert `alerts`.

> Warm-up ≥3 và `drop_pct > 20` **không** còn là điều kiện gửi (MVP notify-on-snapshot).

### Hành vi empty / lỗi

| Tình huống | Hành vi |
|---|---|
| `best_flights` empty/missing | Dùng `other_flights` nếu có; cả hai rỗng → skip snapshot/alert |
| Đã alert cùng key trong 24h | Snapshot vẫn ghi; **không** gửi Telegram lại |
| HTTP 429 | Log; retry 1 lần sau ~5s; không chặn route khác |
| 401/403 / timeout sau retry | Ghi lỗi; tiếp tục route khác |
| Load BQ fail | Không Transform/Alert cho run đó; log rõ |
| Overlap 2 job | Một runner (file lock đơn giản) |

---

## 9. Kênh cảnh báo

- **Telegram only** `[MVP DECISION]`
- Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### Nội dung message tối thiểu

- Route label + IATA (`DAD → SGN`)
- `departure_month` (ngày bay mẫu)
- `price` (VND)
- Mỗi leg từ `flights_json`: `flight_number`, `airplane`, `travel_class`, dep/arr IATA + time, `duration`
- `total_duration` / `transfers` khi multi-leg
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

- `SERPAPI_API_KEY`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `GCP_PROJECT_ID`, `BQ_DATASET`, `GCS_BUCKET`
- `GOOGLE_APPLICATION_CREDENTIALS` (path tới SA JSON)

---

## 12. Smoke test ngày 1

```python
import serpapi

client = serpapi.Client(api_key="<SERPAPI_API_KEY>")
results = client.search({
  "engine": "google_flights",
  "departure_id": "DAD",
  "arrival_id": "HAN",
  "currency": "VND",
  "type": "2",
  "outbound_date": "2026-11-10",
})
best_flights = results["best_flights"]
```

Checklist:

1. Có `best_flights` hoặc `other_flights` và phần tử có `price`
2. Currency trong config là `VND`
3. Thử lần lượt `SGN`, `BKK`, `SIN`, `PQC`
4. Chạy 1 cycle pipeline: raw xuất hiện trên BQ **trước** khi Transform

---

## 13. Acceptance Criteria

1. **Schedule:** Pipeline chạy đúng 5 mốc ICT mỗi ngày.
2. **Origin:** Mọi watched request có `origin=DAD` và đúng 5 destination đã khóa.
3. **ELT raw-first:** Mỗi call được Load vào BigQuery `raw_flight_prices` (NDJSON load) **trước** Transform.
4. **Snapshot:** Khi có giá, SQL ghi `min(price)` vào `price_snapshots`.
5. **Alert:** Có snapshot giá → Telegram đủ field chuyến bay (`flights_json`); ghi `alerts`.
6. **Anti-spam:** Không gửi lại cùng key trong 24h.
7. **API hygiene:** SerpAPI `engine=google_flights`; currency từ `config/serpapi_query.json`.
8. **No CSV on hot path:** Staging raw là NDJSON, không CSV.
9. **Deploy:** Chạy trên VPS bằng Cron + SA; secret không nằm trong git.
10. **Narrative:** Bảo vệ gọi đúng **ELT** + BigQuery; nêu date-sampling (1 ngày/tháng).

---

## 14. Implementation checklist

- [x] `docs/MVP_SPEC.md` (BigQuery ELT)
- [ ] Smoke test SerpAPI với key thật (`DAD-HAN` trước)
- [x] Tạo DDL/SQL BQ (`sql/bq_ddl.sql`, `sql/bq_transform.sql`)
- [x] `config/routes.json` (5 chặng DAD-*)
- [x] `config/serpapi_query.json` (query params)
- [x] Worker: extract → stage NDJSON → load → transform SQL → alert
- [x] Cron template 5 slots + TZ (`crontab`)
- [x] `.env.example` + `.gitignore` (SA key)
- [ ] Deploy VPS + thử 1 run tay (cần GCP + SerpAPI key thật)
- [x] README: cách chạy, ELT, date-sampling SerpAPI

---

## 15. Rủi ro đã biết

| Risk | Mitigation |
|---|---|
| SerpAPI cần ngày, MVP so theo tháng | 1 ngày mẫu/tháng; nêu rõ trong báo cáo |
| Quota / billing SerpAPI | Theo dõi 75 searches/ngày |
| CSV làm mất nested JSON | Chỉ NDJSON cho raw |
| SA key / SerpAPI key lộ | `.gitignore`; không commit |
| Một số chặng data mỏng | Smoke test; đổi destination sau nếu cần |
| Anti-spam 24h chặn demo liên tiếp | Đợi 24h hoặc xóa row `alerts` test |

---

## 16. Changelog quyết định khóa

| Quyết định | Giá trị |
|---|---|
| Origin | Luôn `DAD` |
| Destinations | `HAN`, `SGN`, `BKK`, `SIN`, `PQC` |
| Alert trigger | Có `price_snapshots` trong run (notify-on-snapshot) |
| Flight detail | Option B: `flights_json` + `total_duration` trên snapshot |
| Anti-spam | 24 giờ / baseline key |
| Channel | Telegram only |
| Currency param | `currency=VND` (config) |
| Source | SerpAPI `google_flights` / `best_flights` (fallback `other_flights`) |
| Date sampling | 1 `outbound_date` / tháng |
| Horizon | Tháng hiện tại + 2 tháng |
| Architecture | **ELT** |
| Warehouse | **BigQuery** (thay PostgreSQL) |
| Staging | **NDJSON → GCS → Load Job** (không CSV raw) |
| Transform | **SQL trên BigQuery** |

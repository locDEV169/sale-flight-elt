# Deploy Option A — Cloud Run Job + Cloud Scheduler

Batch ELT worker (`python main.py`) trên Google Cloud: **không** giữ HTTP server 24/7.

```text
Cloud Scheduler (ICT 00/05/10/15/20)
  → Cloud Run Job
  → python main.py
      SerpAPI → NDJSON → GCS → BigQuery → Telegram
```

Region khuyến nghị: **`asia-southeast1`** (khớp `BQ_LOCATION`).

---

## 0. Preconditions (đã có trong project này)

- [ ] GCP project + billing ON
- [ ] BigQuery dataset (vd. `flight_elt`) + schema (`scripts/init_bq_schema.py`)
- [ ] GCS bucket (vd. `flight-elt`)
- [ ] SerpAPI key + Telegram bot/chat hoạt động local (`python main.py` / `check_telegram.py`)
- [ ] `gcloud` CLI đã login: `gcloud auth login` + `gcloud config set project PROJECT_ID`

Đặt biến local (thay giá trị của bạn):

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="asia-southeast1"
export REPO="sale-flight"
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/elt:latest"
export JOB_NAME="sale-flight-elt"
export SA_RUN="sale-flight-runner@${PROJECT_ID}.iam.gserviceaccount.com"
export SA_SCHEDULER="sale-flight-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
export BQ_DATASET="flight_elt"
export GCS_BUCKET="flight-elt"
```

---

## 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  --project="${PROJECT_ID}"
```

- [ ] APIs enabled

---

## 2. Service accounts + IAM

### 2.1 Runtime SA (Cloud Run Job)

```bash
gcloud iam service-accounts create sale-flight-runner \
  --display-name="sale-flight Cloud Run Job" \
  --project="${PROJECT_ID}"
```

Gắn quyền tối thiểu:

```bash
# BigQuery
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/bigquery.jobUser"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/bigquery.dataEditor"

# GCS bucket staging/raw
gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/storage.objectAdmin"

# Đọc secrets
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_RUN}" \
  --role="roles/secretmanager.secretAccessor"
```

- [ ] `sale-flight-runner` created
- [ ] BQ + GCS + Secret Accessor OK

> Job dùng **ADC của attached SA** → **không** cần `GOOGLE_APPLICATION_CREDENTIALS` file trong container.

### 2.2 Scheduler SA (invoke Job)

```bash
gcloud iam service-accounts create sale-flight-scheduler \
  --display-name="sale-flight Scheduler" \
  --project="${PROJECT_ID}"

# Cho phép Scheduler SA chạy Job (gắn sau khi Job tồn tại — step 6 cũng nhắc lại)
```

- [ ] `sale-flight-scheduler` created

---

## 3. Secret Manager

**Khuyến nghị:** sync từ `.env` local (không paste key vào shell history nếu có thể tránh):

```bash
export PROJECT_ID=project-81bd20d6-d241-49b7-acf
./scripts/sync_job_secrets_from_env.sh
# → create/add versions SERPAPI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# → bind :latest onto Cloud Run Job + update HORIZON_DAYS
gcloud run jobs execute sale-flight-elt --region=asia-southeast1 --project="${PROJECT_ID}" --wait
```

Tạo tay (nếu cần):

```bash
printf '%s' 'REAL_KEY' | gcloud secrets create SERPAPI_API_KEY \
  --data-file=- --replication-policy=automatic --project="${PROJECT_ID}"
# hoặc versions add nếu đã có secret
```

Job YAML dùng `valueFrom` / `--set-secrets` — **không** nhét key plain vào YAML. Nếu log thấy `api_key=YOUR_SERPAPI_KEY` → secret đang placeholder, chạy sync script.

- [ ] `SERPAPI_API_KEY`
- [ ] `TELEGRAM_BOT_TOKEN`
- [ ] `TELEGRAM_CHAT_ID`

---

## 4. Artifact Registry + image

### 4.1 Repo

```bash
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}"
```

(Bỏ qua nếu repo đã có.)

### 4.2 Dockerfile (repo root — tạo trước khi build)

Checklist nội dung tối thiểu:

- [ ] Base `python:3.12-slim` (hoặc 3.11)
- [ ] `pip install -r requirements.txt`
- [ ] `COPY` source (`main.py`, `elt/`, `config/`, `sql/`, …)
- [ ] Tạo sẵn `staging/` (writable) — pipeline ghi NDJSON + lock tại `ROOT/staging`
- [ ] `CMD ["python", "main.py"]`
- [ ] **Không** `COPY` `.env` / SA JSON vào image

Ví dụ skeleton:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY elt/ elt/
COPY config/ config/
COPY sql/ sql/
RUN mkdir -p staging
CMD ["python", "main.py"]
```

### 4.3 Build & push

```bash
gcloud builds submit --tag "${IMAGE}" --project="${PROJECT_ID}"
```

- [ ] Image pushed: `${IMAGE}`

---

## 5. Cloud Run Job

```bash
gcloud run jobs create "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --service-account="${SA_RUN}" \
  --memory=1Gi \
  --cpu=1 \
  --task-timeout=15m \
  --max-retries=0 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},BQ_DATASET=${BQ_DATASET},BQ_LOCATION=${REGION},GCS_BUCKET=${GCS_BUCKET},HORIZON_DAYS=0" \
  --set-secrets="SERPAPI_API_KEY=SERPAPI_API_KEY:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest"
```

Update sau này:

```bash
gcloud run jobs update "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}"
```

- [ ] Job created
- [ ] Env non-secret set
- [ ] Secrets mapped

---

## 6. Cho Scheduler quyền chạy Job

```bash
gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_SCHEDULER}" \
  --role="roles/run.invoker"
```

- [ ] Scheduler SA = `run.invoker` trên Job

---

## 7. Cloud Scheduler (5 mốc ICT)

Một cron đủ 5 slot (giống `crontab` trong repo):

```bash
gcloud scheduler jobs create http sale-flight-elt-cron \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --schedule="0 0,5,10,15,20 * * *" \
  --time-zone="Asia/Ho_Chi_Minh" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
  --http-method=POST \
  --oauth-service-account-email="${SA_SCHEDULER}" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

> Nếu API URI đổi theo version `gcloud`, dùng Console: **Cloud Scheduler → Run Job target**, hoặc:
> `gcloud run jobs execute` documented HTTP target từ Cloud Console “Create scheduler”.

- [ ] Schedule `0 0,5,10,15,20 * * *`
- [ ] Time zone `Asia/Ho_Chi_Minh`
- [ ] OAuth SA = scheduler SA

---

## 8. Verify + cách check log (Job / “cron”)

Cloud Scheduler chỉ **trigger**; log nghiệp vụ nằm ở **Cloud Run Job executions**.

### 8.1 Chạy tay 1 lần

```bash
gcloud run jobs execute "${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --wait
```

### 8.2 Liệt kê executions (đã chạy chưa?)

```bash
gcloud run jobs executions list \
  --job="${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}"
```

Chi tiết 1 execution:

```bash
# thay EXECUTION_NAME, vd. sale-flight-elt-ff7mb
gcloud run jobs executions describe EXECUTION_NAME \
  --region="${REGION}" \
  --project="${PROJECT_ID}"
```

**Console:** Cloud Run → Jobs → `sale-flight-elt` → **Executions**  
(hoặc URL dạng  
`https://console.cloud.google.com/run/jobs/executions/details/asia-southeast1/EXECUTION_NAME?project=PROJECT_NUMBER`)

### 8.3 Đọc log pipeline (Cloud Logging)

Log theo **một execution**:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="'"${JOB_NAME}"'" AND labels."run.googleapis.com/execution_name"="EXECUTION_NAME"' \
  --project="${PROJECT_ID}" \
  --limit=50 \
  --format='value(textPayload)'
```

Log **mọi lần chạy** Job gần đây (kèm timestamp):

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="'"${JOB_NAME}"'"' \
  --project="${PROJECT_ID}" \
  --limit=50 \
  --format='value(timestamp,textPayload)'
```

**Console:** Execution → tab **Logs**  
hoặc Logging → truy vấn  
`resource.type="cloud_run_job" resource.labels.job_name="sale-flight-elt"`

Expect khi healthy:

- [ ] `starting extract`
- [ ] SerpAPI `status=200` (không phải 401)
- [ ] `loaded N rows into …raw_flight_prices`
- [ ] `transform finished`
- [ ] `alert candidates: N` / `alerts_sent: N` / `Container called exit(0)`

| Log thấy | Ý nghĩa |
|---|---|
| `exit(0)` + `alerts_sent=0` + `candidates=0` | Job OK về container; xem thêm dòng `extracted … error=` |
| `serpapi body error` + *hasn't returned any results* | Google Flights **không có vé** cho query (thường ngày bay quá gần / hết chỗ) → không snapshot → không Telegram |
| `401` / `YOUR_SERPAPI_KEY` | Secret `SERPAPI_API_KEY` sai / placeholder → sync secret |
| `status=200` + `n_best`/`n_other` > 0 | Extract OK |
| `candidates=0` sau khi đã có snapshot | Thường **anti-spam 24h** |
| Execution `Failed` | Vào describe + Logs xem exception |

Cập nhật secret rồi chạy lại Job (không cần rebuild image):

```bash
printf '%s' 'REAL_SERPAPI_KEY' | gcloud secrets versions add SERPAPI_API_KEY \
  --data-file=- --project="${PROJECT_ID}"
gcloud run jobs execute "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --wait
```

### 8.4 Data + Telegram

- [ ] BigQuery: row mới trong `raw_flight_prices` / `price_snapshots`
- [ ] Nếu `candidates=0`: kiểm tra **anti-spam 24h** trên `alerts` (không phải lỗi deploy)
- [ ] Telegram nhận message khi có candidate

### 8.5 Cloud Scheduler (“cron”) — check đã fire chưa

```bash
# Trạng thái cron
gcloud scheduler jobs describe sale-flight-elt-cron \
  --location="${REGION}" \
  --project="${PROJECT_ID}"

# Fire tay 1 lần
gcloud scheduler jobs run sale-flight-elt-cron \
  --location="${REGION}" \
  --project="${PROJECT_ID}"

# Sau đó list executions Job — phải có execution mới
gcloud run jobs executions list \
  --job="${JOB_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}"
```

Log Scheduler (trigger HTTP), khác log pipeline:

```bash
gcloud logging read \
  'resource.type="cloud_scheduler_job" AND resource.labels.job_id="sale-flight-elt-cron"' \
  --project="${PROJECT_ID}" \
  --limit=20 \
  --format='value(timestamp,textPayload,jsonPayload)'
```

**Console:** Cloud Scheduler → `sale-flight-elt-cron` → lịch sử / rồi sang Cloud Run Executions để đọc log `main.py`.

- [ ] Schedule `0 0,5,10,15,20 * * *`
- [ ] Time zone `Asia/Ho_Chi_Minh`
- [ ] OAuth SA = scheduler SA
- [ ] Trigger tạo execution Job mới trên Cloud Run

---

## 9. Ops / rollback

| Việc | Cách |
|---|---|
| Đổi code | Build image mới → `gcloud run jobs update` / `./scripts/deploy_cloud_run.sh` |
| Pause schedule | `gcloud scheduler jobs pause sale-flight-elt-cron …` |
| Xem executions | Console → Cloud Run → Jobs → Executions |
| Xem log | §8.3 / tab Logs của execution |
| Rollback image | Update Job về tag/digest cũ |
| Demo spam Telegram | Xóa/đợi anti-spam trên `alerts`, hoặc tạm pause scheduler |

---

## 10. Cost notes (MVP)

- Cloud Run Job: chỉ tính khi chạy (~5 × vài phút/ngày) → thường rất thấp
- Scheduler: free tier nhỏ / vài job
- Artifact Registry + logs: nhỏ
- Chi phí chính vẫn là **BigQuery + SerpAPI** (ngoài GCP billing SerpAPI)

---

## 11. Repo artifacts

| File | Vai trò |
|---|---|
| `Dockerfile` | Image chạy `python main.py` |
| `.dockerignore` | Loại `.env`, secrets, staging raw, tests/docs |
| `scripts/deploy_cloud_run.sh` | Build + create/update Job (cần IAM/secrets/scheduler làm trước theo §§1–3,6–7) |

```bash
export PROJECT_ID=...
export GCS_BUCKET=...
# optional: REGION REPO JOB_NAME BQ_DATASET SA_RUN HORIZON_DAYS
./scripts/deploy_cloud_run.sh
# deploy xong chạy execute lại
gcloud run jobs execute sale-flight-elt --region=asia-southeast1 --project=$PROJECT_ID --wait
```

Local vẫn dùng `.env` + SA JSON; trên Job dùng attached SA (không set `GOOGLE_APPLICATION_CREDENTIALS`).

---

## 12. Done criteria

- [x] Job execute tay thành công (exit 0) — xem §13
- [ ] Scheduler fire được Job (chưa bắt buộc nếu chưa tạo cron §7)
- [ ] Raw land BQ trước transform (đúng ELT) — cần SerpAPI key thật trong Secret Manager
- [ ] Telegram alert khi có candidate và không dính anti-spam
- [x] Secret không nằm trong image / git (dùng Secret Manager)

---

## 13. Nhật ký deploy thực tế (project này)

Project: `project-81bd20d6-d241-49b7-acf` · Region: `asia-southeast1`  
Job: `sale-flight-elt` · Image repo: `sale-flight/elt:latest`  
Runtime SA: `sale-flight-runner@…`

### Đã làm (theo thứ tự gặp lỗi → fix)

| # | Bước | Kết quả |
|---|---|---|
| 1 | Artifact Registry repo `sale-flight` | OK |
| 2 | Enable Cloud Build API | OK |
| 3 | IAM Compute SA đọc bucket `{project}_cloudbuild` | Fix 403 `storage.objects.get` |
| 4 | IAM Compute SA `artifactregistry.writer` (+ `logging.logWriter`) | Fix push image denied |
| 5 | `gcloud builds submit` / `./scripts/deploy_cloud_run.sh` | Image push **SUCCESS** |
| 6 | Tạo SA `sale-flight-runner` + user `actAs` (`roles/iam.serviceAccountUser`) | Fix `iam.serviceaccounts.actAs` denied |
| 7 | Enable Secret Manager API + tạo secrets + `secretAccessor` cho runner | Fix Secret Manager disabled |
| 8 | Create/update Cloud Run Job (`deploy_cloud_run.sh`) | **OK: deploy done** |
| 9 | `gcloud run jobs execute … --wait` | Execution **`sale-flight-elt-ff7mb`** completed successfully (~29s) |

### Chưa / việc tiếp

| # | Bước | Ghi chú |
|---|---|---|
| A | Cloud Scheduler `sale-flight-elt-cron` (§7) | Chưa thấy xác nhận trong session deploy; làm khi muốn 5 mốc/ngày |
| B | Secret `SERPAPI_API_KEY` giá trị thật | Log `ff7mb` có `401` + `api_key=YOUR_SERPAPI_KEY` → đang placeholder; `versions add` key thật rồi execute lại |
| C | `alerts_sent` | Lần `ff7mb`: `candidates=0` (sau 401 extract `status=0`); sau khi key đúng còn có thể dính anti-spam 24h |

### Lệnh check nhanh (copy)

```bash
export PROJECT_ID=project-81bd20d6-d241-49b7-acf
export REGION=asia-southeast1
export JOB_NAME=sale-flight-elt

gcloud run jobs executions list --job="${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}"

gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="sale-flight-elt"' \
  --project="${PROJECT_ID}" --limit=30 \
  --format='value(timestamp,textPayload)'
```

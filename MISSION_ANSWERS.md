# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Các anti-pattern tìm thấy trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secret (`OPENAI_API_KEY`, `DATABASE_URL`)** — dòng 17–18:
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Nếu push lên GitHub public, key và mật khẩu bị lộ ngay lập tức (kể cả khi xoá ở commit sau thì vẫn nằm trong lịch sử git); muốn đổi key phải sửa code và deploy lại.
2. **Hardcode cấu hình (`DEBUG`, `MAX_TOKENS`)** — dòng 21–22:
   - `DEBUG = True` và `MAX_TOKENS = 500` được gán cứng trong code thay vì đọc từ biến môi trường, vi phạm nguyên tắc 12-Factor tách config khỏi code giữa dev/staging/prod.
3. **Dùng `print()` thay cho logging chuẩn & làm lộ secret** — dòng 33–38:
   - Dòng 34 in trực tiếp `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`, làm lộ API key ra stdout/log collector, đồng thời không có định dạng JSON hay log level.
4. **Không có endpoint health check và readiness** — dòng 42–43:
   - Thiếu `/health` (liveness) và `/ready` (readiness), nên nền tảng cloud hoặc load balancer không biết container bị treo để restart hay đã sẵn sàng nhận traffic chưa.
5. **Gán cứng `host="localhost"`, `port=8000` và `reload=True`** — dòng 49–54:
   - Bind `localhost` khiến bên ngoài container không kết nối được; gán cứng `port=8000` bỏ qua biến `PORT` do Railway/Render cấp; bật `reload=True` gây tốn tài nguyên và không an toàn trên production.
6. **Không xử lý graceful shutdown / `SIGTERM`**:
   - Không có `lifespan` hay signal handler cho `SIGTERM`, nên khi tắt hoặc redeploy container có thể cắt ngang request đang xử lý.

### Exercise 1.2: Kết quả chạy bản develop
Lệnh chạy trong WSL2:
```bash
curl -i -sS -X POST "http://localhost:8000/ask?question=Hello"
```
Kết quả thực tế:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:05:07 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```
*(Trong stdout của server cũng in ra `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`, cho thấy secret bị rò rỉ ra log.)*

### Exercise 1.3: Bảng so sánh (`develop` vs `production`)

| Tiêu chí | Develop (`develop/app.py`) | Production (`production/app.py` & `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True`) | Đọc từ biến môi trường qua dataclass `Settings` trong `config.py` (`os.getenv(...)`) kèm `validate()` fail-fast | Tránh lộ secret lên Git và thay đổi cấu hình theo môi trường mà không cần sửa code. |
| **Host & Port** | `host="localhost"`, `port=8000`, `reload=True` | `host=settings.host` (`0.0.0.0`), `port=settings.port` (biến `PORT`), `reload=settings.debug` | `0.0.0.0` cho phép nhận kết nối từ ngoài container; cloud platform cấp cổng động qua `PORT`. |
| **Health & Readiness** | Không có | `GET /health` (liveness kèm uptime, version, timestamp) và `GET /ready` (trả `503` khi `is_ready` là `False`) | Nền tảng cần `/health` để tự restart container lỗi và `/ready` để chỉ route traffic khi app sẵn sàng. |
| **Logging** | `print()` và in cả API key | `logging` chuẩn JSON (`{"time":...,"level":...,"msg":...}`), chỉ log `question_length` và `client_ip` | Log JSON dễ thu thập và phân tích bằng Loki/Datadog, không làm lộ dữ liệu nhạy cảm. |
| **Shutdown** | Tắt đột ngột, không có lifecycle hook | `lifespan` của FastAPI + `signal.signal(signal.SIGTERM, handle_sigterm)` | Giúp các request đang chạy được hoàn tất trước khi container tắt khi rolling deploy/scale down. |
| **CORS & Input** | Không cấu hình CORS; nhận `question` qua query param | `CORSMiddleware` đọc từ `ALLOWED_ORIGINS`; `POST /ask` nhận JSON body và validate `question` rỗng (422) | Kiểm soát origin được phép gọi API và chuẩn hoá contract JSON đầu vào. |

**Ví dụ lỗi đã được sửa từ `develop/app.py` sang `production/app.py`:**
- Ở `01-localhost-vs-production/develop/app.py` (dòng 49–54), server cấu hình cứng `host="localhost"`, `port=8000`, `reload=True`.
- Sang `01-localhost-vs-production/production/app.py` (dòng 194–199) và `config.py` (dòng 17–19), cấu hình này được sửa thành đọc từ biến môi trường:
  ```python
  uvicorn.run(
      "app:app" if settings.debug else app,
      host=settings.host,   # mặc định 0.0.0.0
      port=settings.port,   # đọc từ biến môi trường PORT
      reload=settings.debug,
  )
  ```
- Tương tự, `OPENAI_API_KEY` hardcode và `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (`develop/app.py` dòng 17, 34) được thay bằng `os.getenv("OPENAI_API_KEY", "")` (`config.py` dòng 27) và JSON logging không chứa secret (`production/app.py` dòng 28–31, 111–122).

---

## Part 2: Docker

### Exercise 2.1: Trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`
1. **Base image là gì?**
   - `python:3.11` (dòng 8) — bản phân phối Python đầy đủ (~1 GB), chứa sẵn nhiều công cụ hệ thống không cần thiết khi chạy runtime.
2. **Working directory là gì?**
   - `/app` (dòng 11: `WORKDIR /app`). Mọi lệnh `COPY`, `RUN`, `CMD` sau đó đều chạy tương đối trong `/app`.
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY . .` (hoặc copy source code)?**
   - Để tận dụng **Docker layer cache**. Docker cache từng layer theo thứ tự lệnh; khi chỉ sửa code (`app.py`) mà không đổi `requirements.txt`. Những phần nào ít thay đổi thì để lên đầu giúp build lại cực nhanh thay vì tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `ENTRYPOINT` định nghĩa file thực thi/lệnh chính cố định của container (khó bị ghi đè ngoài ý muốn; tham số truyền thêm ở `docker run` sẽ nối vào sau `ENTRYPOINT`).
   - `CMD` định nghĩa lệnh hoặc tham số mặc định khi chạy container, nhưng **dễ dàng bị ghi đè** nếu người dùng truyền lệnh mới sau tên image trong `docker run <image> <command>`.

### Exercise 2.2: Build và chạy container `my-agent:develop`
Build từ gốc repo và chạy container:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name cp2-dev -p 8000:8000 my-agent:develop
curl -i -sS -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
```
Kết quả thực tế:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:18:32 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: So sánh kích thước image (Multi-stage build)
Kết quả đo thực tế bằng `docker images` (sau khi build `my-agent:develop` và `my-agent:advanced` từ gốc repo):
```text
REPOSITORY   TAG        IMAGE ID       DISK USAGE   CONTENT SIZE
my-agent     advanced   884b9cd05d02   240MB        57.4MB
my-agent     develop    efa1f38b0d7e   1.67GB       426MB
```
- **Develop (`my-agent:develop`):** `1.67 GB` (`1,670 MB`) — content size `426 MB`
- **Production (`my-agent:advanced`):** `240 MB` — content size `57.4 MB`
- **Chênh lệch:** Giảm **~85.6%** dung lượng trên đĩa (`(1670 - 240) / 1670 ≈ 85.6%`, và content size giảm **~86.5%** từ `426 MB` xuống `57.4 MB`).

**Multi-stage build giảm dung lượng ở đâu?**
- **Stage 1 (`builder`, `python:3.11-slim`):** Cài `gcc`, `libpq-dev` qua `apt-get` và biên dịch/cài dependencies vào `/root/.local`. Toàn bộ compiler và build tools nặng chỉ nằm ở stage này và **không** được đưa vào image cuối.
- **Stage 2 (`runtime`, `python:3.11-slim`):** Chỉ `COPY --from=builder /root/.local /home/appuser/.local` cùng source code (`main.py`, `utils/mock_llm.py`), không có `gcc` hay `apt` cache, đồng thời chạy bằng non-root user `appuser` để tăng bảo mật.

### Exercise 2.4: Docker Compose stack và test qua Nginx
**Sơ đồ kiến trúc các service (`02-docker/production/docker-compose.yml`):**
```mermaid
flowchart LR
    Client["Client (curl / Browser)"] -->|"HTTP :80 / HTTPS :443"| Nginx["nginx (nginx:alpine)"]
    subgraph internal["Docker Network: internal (bridge)"]
        Nginx -->|"Reverse Proxy :8000"| Agent["agent (k5-day14-docker-agent)"]
        Agent -->|"REDIS_URL=redis://redis:6379/0"| Redis["redis (redis:7-alpine)"]
        Agent -->|"QDRANT_URL=http://qdrant:6333"| Qdrant["qdrant (qdrant/qdrant:v1.9.0)"]
    end
    Redis --- RedisVol[("Volume: redis_data")]
    Qdrant --- QdrantVol[("Volume: qdrant_data")]
```
- Các service giao tiếp nội bộ qua bridge network `internal` bằng tên service (`agent`, `redis`, `qdrant`). Chỉ `nginx` mở port `80` và `443` ra host; `agent` không mở port trực tiếp.

**Kết quả test qua Nginx (`docker compose -p k5-day14-docker up -d --build`):**
1. `GET http://localhost/health`:
```http
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:22:01 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.7,"version":"2.0.0","timestamp":"2026-11-25T08:22:01.011236"}
```
2. `POST http://localhost/ask`:
```http
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:22:01 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## Part 4: API Security

### Exercise 4.1–4.3: Kết quả test `401`, `200`, và `429` (`curl -i`, đã che token/key)

1. **Bản `develop/` (`04-api-gateway/develop/app.py`) — API Key Authentication:**
   - **Không có `X-API-Key` → `401 Unauthorized`:**
     ```http
     HTTP/1.1 401 Unauthorized
     date: Wed, 25 Nov 2026 08:50:20 GMT
     server: uvicorn
     content-length: 67
     content-type: application/json

     {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
     ```
   - **Có `X-API-Key: <REDACTED_API_KEY>` → `200 OK`:**
     ```http
     HTTP/1.1 200 OK
     date: Wed, 25 Nov 2026 08:50:20 GMT
     server: uvicorn
     content-length: 122
     content-type: application/json

     {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
     ```

2. **Bản `production/` (`04-api-gateway/production/app.py`) — JWT Authentication & Rate Limiting:**
   - **Không có JWT (`Authorization: Bearer <REDACTED_TOKEN>`) → `401 Unauthorized`:**
     ```http
     HTTP/1.1 401 Unauthorized
     date: Wed, 25 Nov 2026 08:49:39 GMT
     server: uvicorn
     www-authenticate: Bearer
     content-length: 76
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"detail":"Authentication required. Include: Authorization: Bearer <token>"}
     ```
   - **Lấy token ở `POST /auth/token` (`student` / `demo123`) và gọi `POST /ask` với `Authorization: Bearer <REDACTED_TOKEN>` → `200 OK`:**
     ```http
     HTTP/1.1 200 OK
     date: Wed, 25 Nov 2026 08:49:40 GMT
     server: uvicorn
     content-length: 216
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":0.000209}}
     ```
   - **Vòng lặp gọi liên tục 11 lần (`student` giới hạn 10 req/phút) → Request 2..10 trả `200`, Request 11 trả `429 Too Many Requests`:**
     ```http
     HTTP/1.1 429 Too Many Requests
     date: Wed, 25 Nov 2026 08:49:41 GMT
     server: uvicorn
     x-ratelimit-limit: 10
     x-ratelimit-remaining: 0
     x-ratelimit-reset: 1795596642
     retry-after: 59
     content-length: 98
     content-type: application/json
     x-content-type-options: nosniff
     x-frame-options: DENY
     x-xss-protection: 1; mode=block
     referrer-policy: strict-origin-when-cross-origin

     {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
     ```

3. **Trả lời câu hỏi `rate_limiter.py` (Exercise 4.3):**
   - **Thuật toán:** Sliding Window Counter (dùng `deque` lưu timestamp các request trong cửa sổ `window_seconds = 60` giây và loại bỏ các timestamp cũ hơn `now - window_seconds`).
   - **Giới hạn:** `rate_limiter_user` cho phép **10 requests/phút** (`max_requests=10, window_seconds=60`); `rate_limiter_admin` cho phép **100 requests/phút**.
   - **Cách bypass/nâng hạn mức cho admin:** Trong `app.py` (dòng 141), đọc `role` từ JWT payload (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`), hoặc có thể bỏ qua bước gọi `limiter.check(...)` nếu `role == "admin"`.

### Exercise 4.4: Cách làm Cost Guard & lý do cần cả Rate Limit lẫn Cost Guard
- **Cách triển khai Cost Guard (`04-api-gateway/production/cost_guard.py`):**
  1. **Kiểm tra trước khi gọi LLM (`check_budget(username)`):**
     - Kiểm tra ngân sách tổng toàn hệ thống (`global_daily_budget_usd = 10.0` USD/ngày); nếu vượt, trả về `503 Service Unavailable`.
     - Kiểm tra ngân sách theo từng user (`daily_budget_usd = 1.0` USD/ngày); nếu vượt, trả về `402 Payment Required`.
  2. **Ghi nhận chi phí sau khi LLM trả lời (`record_usage(...)`):**
     - Tính chi phí dựa trên số token đầu vào (`$0.00015 / 1K input tokens`) và đầu ra (`$0.0006 / 1K output tokens`), cộng dồn vào bản ghi của user và tổng hệ thống, đồng thời log cảnh báo khi đạt `80%` ngân sách (`warn_at_pct = 0.8`).
  3. **Khi đưa lên production (nhiều instance):** Lưu state chi tiêu trong **Redis** (ví dụ key `budget:{user_id}:{YYYY-MM}` dùng `INCRBYFLOAT` + `EXPIRE`) thay vì biến in-memory để các instance dùng chung ngân sách và tự reset theo chu kỳ.
- **Tại sao cần cả Rate Limit và Cost Guard?**
  - **Rate limit** bảo vệ **tốc độ / lưu lượng** (giới hạn số request/phút để chống spam, DDoS, quá tải server).
  - **Cost guard** bảo vệ **tiền / ngân sách LLM** (vì một user vẫn có thể gửi các prompt cực dài tốn rất nhiều token trong khi vẫn ở dưới ngưỡng 10 request/phút, làm đội chi phí API nếu không chặn theo USD/token).

---

## AI log
- **CP1 (`01-localhost-vs-production/`):** Nhờ AI hỗ trợ cài môi trường Python trên WSL2 (`uv` + `.venv`), chạy thử hai bản `develop/app.py` và `production/app.py`, kiểm tra các endpoint `/ask`, `/health`, `/ready` bằng `curl` và tổng hợp câu trả lời vào file này.
- **CP2 (`02-docker/`):** Nhờ AI hỗ trợ vẽ sơ đồ kiến trúc. Đã tự kiểm tra lại số liệu đo và câu trả lời theo `Dockerfile` và `docker-compose.yml`. Ghi lại các mốc đã làm vào Part 2.
- **CP3 (`04-api-gateway/`):** Nhờ AI chạy kiểm chứng lại các endpoint và tổng hợp kết quả `curl -i` (đã che token/key) cùng giải thích `rate_limiter.py`, `cost_guard.py` vào mục Part 4.

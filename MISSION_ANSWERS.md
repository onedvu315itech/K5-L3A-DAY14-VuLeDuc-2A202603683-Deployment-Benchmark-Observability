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

## AI log
- **CP1 (`01-localhost-vs-production/`):** Nhờ AI hỗ trợ cài môi trường Python trên WSL2 (`uv` + `.venv`), chạy thử hai bản `develop/app.py` và `production/app.py`, kiểm tra các endpoint `/ask`, `/health`, `/ready` bằng `curl` và tổng hợp câu trả lời Part 1 vào `MISSION_ANSWERS.md`.

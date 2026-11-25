# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Vũ Lê Đức (`2A202603683`)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 (Ubuntu, Python 3.11.18, Docker Desktop)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo 95% người dùng nhận phản hồi dưới 0,5 giây (tránh che giấu tail latency như dùng average). |
| Error rate `/ask` | < 2.0 % | Chấp nhận tỉ lệ lỗi upstream nhỏ (`MOCK_ERROR_RATE=0.01`), tương ứng error budget 2%. |
| Accuracy trên golden dataset | ≥ 80 % | Đảm bảo agent trả lời đúng tối thiểu 80% bộ câu hỏi chuẩn và không bị regression trước khi merge/deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.22 | 188.9 | 219.6 | 1694.8 | 0.67% | PASS |
| 10 | 32.98 | 193.0 | 223.7 | 1707.0 | 1.67% | PASS |
| 50 | 95.63 | 223.3 | 622.3 | 1752.4 | 0.67% | FAIL (p95 > 500ms) |
| 100 | 49.45 | 766.2 | 3837.2 | 4442.4 | 0.33% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Không.** Từ `concurrency=1` lên `10` và `50`, RPS tăng mạnh (`4.22 → 32.98 → 95.63 req/s`), nhưng khi lên `100` thì RPS **tụt xuống `49.45 req/s`** còn p50/p95 tăng vọt (`766.2 ms` / `3837.2 ms`).
- **Nguyên nhân:** Một process Uvicorn đơn lẻ (single worker) bị bão hoà event loop / CPU / giới hạn kết nối khi 100 request dồn vào cùng lúc, gây xếp hàng (queueing delay) làm latency tăng mạnh và throughput giảm.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 190.1 | 219.2 | 239.8 |
| 0.03 (mặc định) | 238.1 | 222.8 | 1692.0 |
| 0.1 | 301.1 | 1670.0 | 1705.1 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **p99** (và **p95** khi tỉ lệ chậm đạt 10%) nhạy nhất với request chậm: chỉ với 3% request chậm (`MOCK_SLOW_RATE=0.03`), `p99` nhảy từ `239.8 ms` lên `1692.0 ms` (gấp ~7 lần), trong khi `avg` chỉ nhích nhẹ từ `190.1 ms` lên `238.1 ms`. Khi tăng lên 10% (`0.1`), `p95` cũng vọt lên `1670.0 ms`.
- **Vì sao không đặt SLO theo average:** Giá trị trung bình bị các request nhanh kéo xuống nên che giấu trải nghiệm tệ của nhóm người dùng ở đuôi phân phối (tail latency). Đặt SLO theo `p95`/`p99` phản ánh đúng ngưỡng chậm mà 1–5% người dùng thực tế phải chờ.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.3 | 109.1 | 112.8 |
| Tổng cost (USD) | $0.000408 | $0.000762 | $0.000783 |
| Cost / câu đúng (USD) | $0.00040755 | $0.00003627 | $0.00003404 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry từ khoá `["jwt", "api key", "xác thực"]` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích JWT có chữ ký số và thời gian hết hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry từ khoá `["kubernetes", "hpa", "chỉ số"]` vào `KNOWLEDGE_BASE` mô tả HPA scale theo CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- Agent `v2` (có bước retrieval RAG) tốn nhiều token hơn (~`109–113` vs `57.3` tokens/câu) và `p95` latency nhỉnh hơn (~`213–216 ms` vs `188.9 ms`), nhưng accuracy tăng từ **`4.3%` lên `100%`**. Nhờ vậy **`cost / câu đúng`** của `v2` (`$0.00003404`) rẻ hơn **~12 lần** so với `v1` (`$0.00040755`).

**Cách dùng exit code của `run_eval.py` trong CI để chặn merge (Exercise 7.3):**

- Khi chạy thử `python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json`, script phát hiện accuracy tụt và 20 câu bị regression nên in `Quality gate ... ❌ FAIL` và trả **`exit code = 1`** (còn đạt chuẩn như `eval_v2_fixed.json` thì trả **`exit code = 0`**).
- Trong GitHub Actions, thêm step chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.8 --baseline reports/eval_v2.json` (bật server v2 tạm thời trước đó); nếu `exit code != 0`, job CI tự động fail và GitHub branch protection sẽ **chặn merge PR**.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với ≥ 2 alert cùng **firing** (`screenshots/prometheus-alert-firing.png`)

### 4.2 Thí nghiệm "phá hệ thống"

*(Đã kiểm tra unit test `promtool test rules /p/alert_rules_test.yml` → `SUCCESS`. Chạy Locust 30 users với `.env` cấu hình `MOCK_ERROR_RATE=0.2`, `MOCK_SLOW_RATE=0.3`, `LLM_MODEL=mock-llm-large`.)*

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | `72s` (`pending` từ `11s`) | Golden Signals → **Error rate** & **LLM calls ok/error** |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | `127s` (`pending` từ `11s`) | **Latency & Traffic (p50/p95/p99)** & **LLM p95** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | `pending` từ `17s` (firing sau ~`2m17s`) | **Cost USD/giờ** & **LLM tokens/s** |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`for: 30s`) | ~`30–45s` (theo rule `up == 0` với `for: 30s`) | **Instances up** & **req/s theo instance** |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | — | **Retrieval hit ratio**, **tokens/s**, bảng **version** |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Alert hạ tầng chỉ bắt được lỗi 5xx, latency cao hoặc sập instance, **không** bắt được suy giảm chất lượng trả lời (accuracy tụt từ 100% xuống 4.3% khi chạy nhầm `v1`).
- **Cách phát hiện:** Chạy **eval tự động (`run_eval.py`) trên golden dataset trong CI/CD** trước khi deploy (quality gate), kết hợp theo dõi **retrieval hit ratio**, **output tokens/s**, và thu thập **user feedback (thumbs up/down)** hoặc **LLM-as-a-judge online sampling** trên production.

### 4.3 Debug bằng trace

Chọn 1 trace chậm tìm được từ log & Jaeger:

- `trace_id` (slow trace): `f45fd1f9bc91603a504de264a79be10f`
- Tổng thời gian: `1722.6 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1692.9 ms`, **`98.3%`** tổng thời gian request; phần còn lại ~`29.7 ms` là retrieval + FastAPI overhead).
- Dòng log tương ứng (lấy từ `docker compose -p k5-day14-observability logs agent` theo `trace_id`):

```json
{"ts": "2026-11-25T11:13:32.137754+00:00", "level": "INFO", "service": "observable-agent", "instance": "e1f483c075e0", "event": "http_request", "trace_id": "f45fd1f9bc91603a504de264a79be10f", "span_id": "87869ac6aa3714d4", "request_id": "cfbc1f9492cd", "method": "POST", "route": "/ask", "status": 200, "ms": 1722.6}
```

- `trace_id` (error trace): `4daf18ea7f1ab2c513c37cfa8190156e` (`event: "llm_error"`, `Upstream LLM error: 503 Service Unavailable (mock)`).

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.77 | 200 | 280 | 1700 | 65 / 7827 (0.83%) |
| 3 | 65.26 | 200 | 320 | 1700 | 78 / 7768 (1.00%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Không cải thiện `p95` (`280 ms` vs `320 ms`) và RPS giữ nguyên ~`65 req/s`.**
- **Nút thắt:**
  1. **Tải đầu vào của Locust:** 100 user với `wait_time = between(1, 2)` giây chỉ tạo tổng cộng ~65 req/s, chưa làm bão hoà CPU của 1 instance FastAPI bất đồng bộ (async).
  2. **Độ trễ nằm ở Upstream LLM (`llm_request_duration_seconds`):** Mỗi request chờ `MOCK_LATENCY_MS=120 + jitter` (và 3% request chậm +1500ms), nên dù scale lên 3 instance thì thời gian chờ LLM của từng request vẫn không đổi.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Không đánh giá hiệu năng bằng latency trung bình:** `p95`/`p99` mới phản ánh đúng tail latency mà người dùng cuối gặp phải.
  2. **Chất lượng phải đo bằng Eval + Quality Gate trong CI:** Metric hạ tầng xanh không đồng nghĩa agent trả lời đúng (`AGENT_VERSION=v1` vẫn xanh hết nhưng accuracy chỉ 4.3%).
  3. **3 trụ cột Metrics – Traces – Logs liên kết chặt chẽ:** Prometheus/Grafana phát hiện bất thường → Jaeger chỉ ra span chậm/lỗi → `trace_id` giúp truy vết đúng dòng log JSON.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Thêm metric theo dõi **chi phí theo tenant/API key** (`cost_usd` nhưng giới hạn cardinality theo tier), **tỉ lệ cache/retrieval hit**, **rate limit 429 rate**, và **synthetic check từ bên ngoài** để bắt lỗi 502/504 ở tầng Nginx/Load Balancer.

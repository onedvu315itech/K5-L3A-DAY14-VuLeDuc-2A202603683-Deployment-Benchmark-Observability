# Thông tin Deployment — Day 14 Lab (Part 6 Agent)

## Public URL
https://k5-l3a-day14-production.up.railway.app

## Nền tảng
Railway

## Lệnh tự kiểm tra (CP6)

Đặt biến môi trường trước khi chạy (không ghi key thật vào file này):
```bash
export BASE="https://k5-l3a-day14-production.up.railway.app"
export AGENT_API_KEY="<key-cua-ban>"
```

### 1. Liveness (`/health` → 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Kết quả mong đợi: 200
```

### 2. Readiness (`/ready` → 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Kết quả mong đợi: 200
```

### 3. Thiếu API Key (`/ask` → 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Kết quả mong đợi: 401
```

### 4. Có API Key (`/ask` → 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Kết quả mong đợi: 200
```

## Biến môi trường đã đặt trên nền tảng
- `PORT` (do nền tảng tự cấp)
- `ENVIRONMENT=production`
- `REDIS_URL` (trỏ tới Redis service trên nền tảng)
- `AGENT_API_KEY` (đặt qua dashboard/CLI, không ghi vào code)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Ảnh chụp màn hình
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)

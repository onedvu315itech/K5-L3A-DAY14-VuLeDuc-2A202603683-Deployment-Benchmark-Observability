"""Rate limiting (tiêu chí 7) — sliding window lưu trong Redis."""
import time
import uuid
from collections import deque

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

_memory_windows: dict[str, deque[float]] = {}
WINDOW_SECONDS = 60.0


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60 giây theo API key."""
    now = time.time()
    window_start = now - WINDOW_SECONDS
    limit = settings.rate_limit_per_minute

    if r is not None:
        redis_key = f"ratelimit:{key}"
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = (
                max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
                if oldest
                else int(WINDOW_SECONDS)
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex[:8]}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, int(WINDOW_SECONDS) + 5)
        pipe.execute()
        return

    window = _memory_windows.setdefault(key, deque())
    while window and window[0] < window_start:
        window.popleft()
    if len(window) >= limit:
        retry_after = max(1, int(window[0] + WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)

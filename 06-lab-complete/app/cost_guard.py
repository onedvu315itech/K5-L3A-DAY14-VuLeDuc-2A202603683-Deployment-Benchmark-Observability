"""Cost guard (tiêu chí 8) — theo dõi chi phí LLM trong Redis."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_memory_daily_cost = 0.0
_memory_monthly_cost = 0.0


def _keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"budget:daily:{now.strftime('%Y-%m-%d')}",
        f"budget:monthly:{now.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Gọi trước khi gọi LLM. Vượt DAILY_BUDGET_USD hoặc MONTHLY_BUDGET_USD → 402."""
    if r is not None:
        daily_key, monthly_key = _keys()
        daily_spent = float(r.get(daily_key) or 0.0)
        monthly_spent = float(r.get(monthly_key) or 0.0)
    else:
        daily_spent = _memory_daily_cost
        monthly_spent = _memory_monthly_cost

    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Cộng chi phí request vào Redis và trả về chi phí (USD)."""
    global _memory_daily_cost, _memory_monthly_cost
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K

    if r is not None:
        daily_key, monthly_key = _keys()
        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, 2 * 24 * 3600)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, 32 * 24 * 3600)
        pipe.execute()
    else:
        _memory_daily_cost += cost
        _memory_monthly_cost += cost

    return round(cost, 8)

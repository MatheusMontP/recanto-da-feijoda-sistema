import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        current_time = time.monotonic() if now is None else now
        window_start = current_time - self.window_seconds
        hits = self._hits[key]

        while hits and hits[0] <= window_start:
            hits.popleft()

        if len(hits) >= self.max_requests:
            retry_after = max(1, int(self.window_seconds - (current_time - hits[0])))
            return RateLimitDecision(allowed=False, retry_after=retry_after)

        hits.append(current_time)
        return RateLimitDecision(allowed=True)

    def reset(self):
        self._hits.clear()


api_rate_limiter = InMemoryRateLimiter(
    max_requests=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)


async def enforce_api_rate_limit(request: Request):
    client_host = request.client.host if request.client else "unknown"
    key = f"{client_host}:{request.url.path}"
    decision = api_rate_limiter.check(key)

    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Muitas requisições em pouco tempo. Tente novamente em instantes.",
                "retry_after": decision.retry_after,
            },
            headers={"Retry-After": str(decision.retry_after)},
        )

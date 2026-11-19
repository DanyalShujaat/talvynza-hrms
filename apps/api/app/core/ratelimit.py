"""Fixed-window rate limiter with in-memory and Redis backends."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import TooManyRequests


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits[key] if now - t < window_s]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url)

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        k = f"rl:{key}:{int(time.time() // window_s)}"
        pipe = self._r.pipeline()
        pipe.incr(k)
        pipe.expire(k, window_s)
        count, _ = pipe.execute()
        return int(count) <= limit


@lru_cache
def get_limiter():
    s = get_settings()
    return RedisRateLimiter(s.redis_url) if s.redis_url else MemoryRateLimiter()


def rate_limit(name: str, *, limit: int | None = None, window_s: int = 60):
    """FastAPI dependency factory limiting by client IP."""

    def dep(request: Request) -> None:
        s = get_settings()
        if not s.rate_limit_enabled:
            return
        ip = request.client.host if request.client else "unknown"
        if not get_limiter().allow(f"{name}:{ip}", limit or s.auth_rate_limit_per_minute, window_s):
            raise TooManyRequests("Too many requests. Please slow down and try again shortly.")

    return dep

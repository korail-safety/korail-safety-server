"""아주 단순한 메모리 기반 요청 횟수 제한 (서버 1대 기준).

서버를 여러 대로 늘리면 Redis 같은 공용 저장소로 바꿔야 한다.
"""

import time
from collections import defaultdict, deque

from app.core.errors import AppError


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """한도를 넘으면 429 TOO_MANY_REQUESTS"""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            raise AppError(429, "TOO_MANY_REQUESTS", "잠시 후 다시 시도해 주세요.")
        hits.append(now)

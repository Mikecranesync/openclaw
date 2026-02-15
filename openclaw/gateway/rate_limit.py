"""Per-user sliding window rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_per_hour: int = 60) -> None:
        self._max = max_per_hour
        self._windows: dict[str, list[float]] = defaultdict(list)

    def check(self, user_id: str) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_reset). Prunes expired entries."""
        now = time.time()
        window = self._windows[user_id]
        cutoff = now - 3600
        self._windows[user_id] = [t for t in window if t > cutoff]
        window = self._windows[user_id]

        if len(window) >= self._max:
            oldest = min(window)
            return False, int(oldest + 3600 - now)

        window.append(now)
        return True, 0

"""Token-bucket rate limiting for the local API (guards against runaway UIs and agents)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Bucket:
    capacity: float
    refill_per_s: float
    tokens: float
    updated: float


class RateLimiter:
    """Classes: ``read`` (GET), ``write`` (other methods), ``sensitive`` (runs, approvals, tests)."""

    LIMITS = {
        "read": (120.0, 10.0),  # burst 120, 600/min
        "write": (60.0, 4.0),  # burst 60, 240/min
        "sensitive": (20.0, 1.0),  # burst 20, 60/min
    }

    def __init__(self, enabled: bool = True, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.enabled = enabled
        self._clock = clock
        self._buckets: dict[str, Bucket] = {}

    @staticmethod
    def classify(method: str, path: str) -> str:
        if path.startswith("/api/approvals") and method != "GET":
            return "sensitive"
        if path.endswith("/test") or path.startswith("/api/agents/run") or path.endswith("/run"):
            return "sensitive"
        if path == "/api/objectives" and method == "POST":
            return "sensitive"
        return "read" if method in ("GET", "HEAD") else "write"

    def check(self, klass: str) -> float:
        """Return 0 if allowed, else seconds until a token is available."""
        if not self.enabled:
            return 0.0
        capacity, refill = self.LIMITS[klass]
        now = self._clock()
        bucket = self._buckets.get(klass)
        if bucket is None:
            bucket = self._buckets[klass] = Bucket(capacity, refill, capacity, now)
        bucket.tokens = min(bucket.capacity, bucket.tokens + (now - bucket.updated) * bucket.refill_per_s)
        bucket.updated = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return 0.0
        return (1 - bucket.tokens) / bucket.refill_per_s

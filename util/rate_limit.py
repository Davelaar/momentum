
from __future__ import annotations
import time

class TokenBucket:
    def __init__(self, rate_per_sec: float, burst: int):
        self.rate = float(rate_per_sec)
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.timestamp = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        delta = max(0.0, now - self.timestamp)
        self.timestamp = now
        self.tokens = min(self.capacity, self.tokens + delta * self.rate)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

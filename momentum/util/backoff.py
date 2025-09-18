
from __future__ import annotations
import random, time

class CircuitBreaker:
    def __init__(self, fail_threshold: int = 5, cooldown_s: float = 30.0):
        self.fail_threshold = fail_threshold
        self.cooldown_s = cooldown_s
        self.failures = 0
        self.open_until = 0.0

    def record_success(self):
        self.failures = 0
        self.open_until = 0.0

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.open_until = time.time() + self.cooldown_s

    def allow(self) -> bool:
        return time.time() >= self.open_until

def exp_backoff(attempt: int, base: float = 0.5, cap: float = 10.0, jitter: float = 0.3) -> float:
    delay = min(cap, base * (2 ** (attempt - 1)))
    if jitter:
        delta = delay * jitter
        delay = random.uniform(max(0.0, delay - delta), delay + delta)
    return delay

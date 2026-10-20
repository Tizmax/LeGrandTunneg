"""Constant-space, monotonic token buckets; callers never wait for tokens."""

import math
import time


class TokenBucket:
    def __init__(self, rate, burst, clock=time.monotonic):
        if any(isinstance(value, bool) or not math.isfinite(value) or value <= 0
               for value in (rate, burst)):
            raise ValueError("Token bucket rate and burst must be positive and finite")
        if burst < 1:
            raise ValueError("Token bucket burst must allow at least one token")
        self.rate = rate
        self.burst = burst
        self.clock = clock
        self._tokens = float(burst)
        self._updated_at = clock()

    def _refill(self):
        now = self.clock()
        self._tokens = min(self.burst, self._tokens + max(0, now - self._updated_at) * self.rate)
        self._updated_at = max(now, self._updated_at)

    def consume(self) -> bool:
        self._refill()
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True

    def retry_after(self) -> int:
        self._refill()
        return max(1, math.ceil((1 - self._tokens) / self.rate))

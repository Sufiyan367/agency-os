import asyncio
import time
from typing import Optional

class AsyncRateLimiter:
    """
    Token-bucket / delay-based asynchronous rate limiter
    to prevent overwhelming external websites or triggering search bans.
    """
    def __init__(self, requests_per_second: float = 3.0):
        self.delay = 1.0 / max(0.1, requests_per_second)
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_request_time
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
            self.last_request_time = time.monotonic()

default_rate_limiter = AsyncRateLimiter(requests_per_second=4.0)

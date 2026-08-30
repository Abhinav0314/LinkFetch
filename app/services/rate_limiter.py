import asyncio
import random
import time
from app.core.config import settings
from app.core.logging import logger


class RateLimiter:
    """Controls outgoing request concurrency and adds randomized jitter delays."""

    def __init__(self, max_concurrent: int = 3, min_delay_ms: int = 800, max_delay_ms: int = 2500):
        self._max_concurrent = max_concurrent
        self._semaphore: asyncio.Semaphore | None = None
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self._last_request_time = 0.0

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily creates the semaphore inside the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    async def acquire(self) -> None:
        """Acquires the concurrency semaphore and applies human-like jitter delay."""
        sem = self._get_semaphore()
        await sem.acquire()
        try:
            delay_sec = random.uniform(self.min_delay_ms, self.max_delay_ms) / 1000.0
            elapsed = time.time() - self._last_request_time
            if elapsed < delay_sec:
                await asyncio.sleep(delay_sec - elapsed)
            self._last_request_time = time.time()
        except BaseException as e:
            sem.release()
            if not isinstance(e, asyncio.CancelledError):
                logger.warning(f"Rate limiter delay error: {e}")
            raise

    def release(self) -> None:
        """Releases the concurrency semaphore."""
        sem = self._get_semaphore()
        sem.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


rate_limiter = RateLimiter(
    max_concurrent=settings.MAX_CONCURRENT_REQUESTS,
)

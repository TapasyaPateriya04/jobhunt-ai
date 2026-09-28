"""Minimum-interval rate limiter usable from both threads and asyncio code."""
from __future__ import annotations

import asyncio
import threading
import time


class RateLimiter:
    """Ensure at least ``min_interval`` seconds pass between successive turns."""

    def __init__(self, min_interval: float) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        self.min_interval = float(min_interval)
        self._lock = threading.Lock()
        self._next_at = 0.0

    def _reserve(self) -> float:
        """Claim the next slot and return how long the caller must sleep before using it."""
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_at)
            self._next_at = slot + self.min_interval
            return slot - now

    def wait(self) -> None:
        """Block the current thread until it is this caller's turn."""
        delay = self._reserve()
        if delay > 0:
            time.sleep(delay)

    async def await_turn(self) -> None:
        """Asynchronously wait (without blocking the event loop) until it is this caller's turn."""
        delay = self._reserve()
        if delay > 0:
            await asyncio.sleep(delay)

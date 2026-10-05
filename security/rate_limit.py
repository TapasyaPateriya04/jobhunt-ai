"""Minimum-interval rate limiter usable from both threads and asyncio code."""
from __future__ import annotations

import asyncio
import threading
import time


# perf_counter, not monotonic: on Windows time.monotonic() only ticks every 15.6 ms, so a
# turn could start up to a tick early. perf_counter is monotonic too, at sub-microsecond resolution.
_clock = time.perf_counter


class RateLimiter:
    """Ensure at least ``min_interval`` seconds pass between successive turns."""

    def __init__(self, min_interval: float) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        self.min_interval = float(min_interval)
        self._lock = threading.Lock()
        self._next_at = 0.0

    def _reserve(self) -> float:
        """Claim the next slot and return the clock time at which the caller may go."""
        with self._lock:
            slot = max(_clock(), self._next_at)
            self._next_at = slot + self.min_interval
            return slot

    def wait(self) -> None:
        """Block the current thread until it is this caller's turn."""
        slot = self._reserve()
        # Sleep can wake a little early on some platforms, so check the clock again.
        while (remaining := slot - _clock()) > 0:
            time.sleep(remaining)

    async def await_turn(self) -> None:
        """Asynchronously wait (without blocking the event loop) until it is this caller's turn."""
        slot = self._reserve()
        while (remaining := slot - _clock()) > 0:
            await asyncio.sleep(remaining)

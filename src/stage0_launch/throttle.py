"""Client-side throttle (001 D9, minimal V1 version).

Concurrency cap + minimum request interval; recognizes 429 and retries per Retry-After (bounded number of retries).
The 429 path is almost impossible to trigger on the local Conduit and is covered by unit tests (not part of the acceptance criteria).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

Response = dict[str, Any]  # {"status": int, "retry_after": str | None, ...}


class Throttle:
    def __init__(self, max_concurrency: int, min_interval_ms: int, max_retries_429: int = 0):
        self._sem = threading.BoundedSemaphore(max_concurrency)
        self._interval_s = min_interval_ms / 1000.0
        self._max_retries_429 = max_retries_429
        self._lock = threading.Lock()
        self._last_request_at = 0.0

    def _wait_interval(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = self._interval_s - (now - self._last_request_at)
            if delta > 0:
                time.sleep(delta)
            self._last_request_at = time.monotonic()

    def _call(self, fn: Callable[[], Response]) -> Response:
        with self._sem:
            self._wait_interval()
            return fn()

    def run(self, fn: Callable[[], Response]) -> Response:
        """Execute one request; on 429, retry per Retry-After up to the limit and return the final response."""
        response = self._call(fn)
        retries = 0
        while response.get("status") == 429 and retries < self._max_retries_429:
            retry_after = response.get("retry_after")
            try:
                delay = float(retry_after) if retry_after is not None else 1.0
            except ValueError:
                delay = 1.0
            time.sleep(max(delay, 0.0))
            retries += 1
            response = self._call(fn)
        return response

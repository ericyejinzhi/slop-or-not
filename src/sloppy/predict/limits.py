"""A small in-memory sliding-window rate limiter. Per process, so it resets on restart and
is not shared between workers - fine for a single small server, and the reason the limit is
a cost guard rather than a security boundary."""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float, clock=time.monotonic):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record an event for `key` and return True, or return False (recording nothing)
        when `key` already used its allowance inside the window. A limit of 0 or less
        means unlimited."""
        if self.max_events <= 0:
            return True
        now = self._clock()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    def retry_after_seconds(self, key: str) -> int:
        """Seconds until `key` may try again (0 if it may now)."""
        now = self._clock()
        with self._lock:
            events = self._events.get(key)
            if not events:
                return 0
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) < self.max_events:
                return 0
            return max(1, int(self.window_seconds - (now - events[0])) + 1)

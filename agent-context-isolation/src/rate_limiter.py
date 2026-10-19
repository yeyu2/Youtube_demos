import time
from collections import defaultdict

class SlidingWindowRateLimiter:
    def __init__(self, capacity: int, window_seconds: float):
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        if not isinstance(window_seconds, (int, float)) or window_seconds <= 0:
            raise ValueError("window_seconds must be a positive number")
        self.capacity = capacity
        self.window_seconds = float(window_seconds)
        self.buckets = defaultdict(list)

    def allow_request(self, tenant_id: str) -> bool:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise TypeError("tenant_id must be a non-empty string")
        now = time.time()
        boundary = now - self.window_seconds
        history = self.buckets[tenant_id]
        while history and history[0] <= boundary:
            history.pop(0)
        if len(history) < self.capacity:
            history.append(now)
            return True
        return False

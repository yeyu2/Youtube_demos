import unittest
from src.rate_limiter import SlidingWindowRateLimiter

class TestRateLimiter(unittest.TestCase):
    def test_tenant_isolation(self):
        limiter = SlidingWindowRateLimiter(capacity=1, window_seconds=60)
        self.assertTrue(limiter.allow_request("tenant-a"))
        self.assertFalse(limiter.allow_request("tenant-a"))
        self.assertTrue(limiter.allow_request("tenant-b"))

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(capacity=-5, window_seconds=10)

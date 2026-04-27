import json
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.core.errors import http_exception_handler
from app.core.rate_limit import InMemoryRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_allows_requests_within_window(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)

        self.assertTrue(limiter.check("127.0.0.1:/api/test", now=100).allowed)
        self.assertTrue(limiter.check("127.0.0.1:/api/test", now=101).allowed)

    def test_blocks_requests_after_limit_until_window_moves(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)

        limiter.check("127.0.0.1:/api/test", now=100)
        limiter.check("127.0.0.1:/api/test", now=101)
        blocked = limiter.check("127.0.0.1:/api/test", now=102)
        allowed_after_window = limiter.check("127.0.0.1:/api/test", now=161)

        self.assertFalse(blocked.allowed)
        self.assertGreater(blocked.retry_after, 0)
        self.assertTrue(allowed_after_window.allowed)


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_exception_handler_uses_standard_error_envelope(self):
        response = await http_exception_handler(
            None,
            HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Muitas requisições.",
                    "retry_after": 10,
                },
            ),
        )

        payload = json.loads(response.body.decode("utf-8"))

        self.assertEqual(response.status_code, 429)
        self.assertEqual(payload["error"]["code"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(payload["error"]["message"], "Muitas requisições.")
        self.assertEqual(payload["error"]["details"], [{"retry_after": 10}])


if __name__ == "__main__":
    unittest.main()

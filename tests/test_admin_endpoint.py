import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from fastapi import HTTPException

from app.api.endpoints import admin


class AdminEndpointTests(unittest.TestCase):
    def test_rejects_when_admin_token_is_not_configured(self):
        with patch.object(admin, "ADMIN_TOKEN", ""):
            with self.assertRaises(HTTPException) as ctx:
                admin._verify_admin_token("token")

        self.assertEqual(ctx.exception.status_code, 503)

    def test_rejects_invalid_admin_token(self):
        with patch.object(admin, "ADMIN_TOKEN", "secret"):
            with self.assertRaises(HTTPException) as ctx:
                admin._verify_admin_token("wrong")

        self.assertEqual(ctx.exception.status_code, 401)

    def test_accepts_valid_admin_token(self):
        with patch.object(admin, "ADMIN_TOKEN", "secret"):
            admin._verify_admin_token("secret")


if __name__ == "__main__":
    unittest.main()

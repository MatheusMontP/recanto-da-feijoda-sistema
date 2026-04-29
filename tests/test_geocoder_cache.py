import sys
import unittest
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.db import cache
from app.services import geocoder
from app.services.geocoder import _apply_jitter, geocode_address


def _test_db_path() -> str:
    path = PROJECT_ROOT / "tests" / f"_geocache_{uuid.uuid4().hex}.db"
    return str(path)


class GeocoderCacheTests(unittest.TestCase):
    def test_apply_jitter_does_not_mutate_cached_dict(self):
        cached = {"lat": -10.97075, "lon": -37.06333, "display_name": "Aracaju"}

        with patch("app.services.geocoder.random.random", return_value=1.0):
            response = _apply_jitter(cached)

        self.assertEqual(cached["lat"], -10.97075)
        self.assertEqual(cached["lon"], -37.06333)
        self.assertNotEqual(response["lat"], cached["lat"])
        self.assertNotEqual(response["lon"], cached["lon"])

    def test_normalized_variants_share_same_cache_key(self):
        variants = [
            "  Rua João   Pessoa, 123, Aracaju - SE, Brasil ",
            "rua joao pessoa, 123",
            "RUA JOÃO PESSOA, 123 / ARACAJU / SE / BRASIL",
        ]

        keys = {cache.normalize_cache_key(value) for value in variants}

        self.assertEqual(keys, {"rua joao pessoa, 123"})

    def test_does_not_overwrite_positive_with_miss(self):
        db_path = _test_db_path()
        with patch.object(cache, "CACHE_DB", db_path):
            cache._geocode_cache.clear()
            positive = {"lat": -10.0, "lon": -37.0, "display_name": "Aracaju, Sergipe"}

            cache.set_cached_geocode("Rua A, Aracaju - SE", positive)
            cache.set_cached_geocode(" rua a ", None)
            cached, exists = cache.get_cached_geocode("Rua A")

            self.assertTrue(exists)
            self.assertEqual(cached, positive)
        Path(db_path).unlink(missing_ok=True)

    def test_clear_geocode_cache_removes_sqlite_and_memory_entries(self):
        db_path = _test_db_path()
        with patch.object(cache, "CACHE_DB", db_path):
            cache._geocode_cache.clear()
            cache.set_cached_geocode(
                "Rua Cache, Aracaju - SE",
                {"lat": -10.0, "lon": -37.0, "display_name": "Aracaju, Sergipe"},
            )

            result = cache.clear_geocode_cache()
            cached, exists = cache.get_cached_geocode("Rua Cache")

            self.assertEqual(result["deleted_rows"], 1)
            self.assertEqual(result["memory_entries"], 1)
            self.assertFalse(exists)
            self.assertIsNone(cached)
        Path(db_path).unlink(missing_ok=True)


class GeocoderCacheAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = _test_db_path()
        self.db_patch = patch.object(cache, "CACHE_DB", self.db_path)
        self.db_patch.start()
        cache._geocode_cache.clear()
        geocoder.reset_geocoder_counters()

    async def asyncTearDown(self):
        self.db_patch.stop()
        cache._geocode_cache.clear()
        geocoder.reset_geocoder_counters()
        Path(self.db_path).unlink(missing_ok=True)

    async def test_cache_hit_logs_event_and_skips_provider(self):
        cache.set_cached_geocode(
            "Rua Cache Hit, Aracaju - SE",
            {"lat": -10.0, "lon": -37.0, "display_name": "Aracaju, Sergipe"},
        )

        with (
            self.assertLogs("lucromaximo", level="DEBUG") as logs,
            patch("app.services.geocoder._fetch_nominatim", new=AsyncMock(return_value=None)) as provider,
            patch("app.services.geocoder.random.random", return_value=0.5),
        ):
            result = await geocode_address(" rua cache hit ")

        self.assertIsNotNone(result)
        self.assertEqual(provider.await_count, 0)
        self.assertIn("event=cache_hit", "\n".join(logs.output))
        self.assertEqual(geocoder.get_geocoder_counters()["hits"], 1)

    async def test_negative_cache_hit_logs_event_and_skips_provider(self):
        cache.set_cached_geocode("Endereco Inexistente, Aracaju - SE", None)

        with (
            self.assertLogs("lucromaximo", level="DEBUG") as logs,
            patch("app.services.geocoder._fetch_nominatim", new=AsyncMock(return_value=None)) as provider,
        ):
            result = await geocode_address(" endereco inexistente ")

        self.assertIsNone(result)
        self.assertEqual(provider.await_count, 0)
        self.assertIn("event=cache_negative_hit", "\n".join(logs.output))
        self.assertEqual(geocoder.get_geocoder_counters()["negative_hits"], 1)

    async def test_negative_cache_skips_provider_within_ttl(self):
        with (
            patch("app.services.geocoder._fetch_nominatim", new=AsyncMock(return_value=None)) as provider,
            patch("app.services.geocoder.asyncio.sleep", new=AsyncMock()),
        ):
            first = await geocode_address("Endereco Inexistente, 999")
            second = await geocode_address(" endereco inexistente, 999, Aracaju - SE ")

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(provider.await_count, 1)

    async def test_expired_entry_calls_provider_again(self):
        key = cache.normalize_cache_key("Rua Expirada")
        expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        old = {"lat": -10.0, "lon": -37.0, "display_name": "Aracaju, Sergipe"}
        with closing(cache.sqlite3.connect(cache.CACHE_DB)) as conn:
            cache._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO geocache (query, original_query, data, status, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, "Rua Expirada", cache.json.dumps(old), "hit", expired_at),
            )
            conn.commit()

        with (
            self.assertLogs("lucromaximo", level="DEBUG") as logs,
            patch(
                "app.services.geocoder._fetch_nominatim",
                new=AsyncMock(return_value=(-10.1, -37.1, "Rua Expirada, Aracaju, Sergipe")),
            ) as provider,
            patch("app.services.geocoder.asyncio.sleep", new=AsyncMock()),
            patch("app.services.geocoder.random.random", return_value=0.5),
        ):
            result = await geocode_address("Rua Expirada")

        self.assertEqual(provider.await_count, 1)
        self.assertEqual(result["lat"], -10.1)
        self.assertEqual(result["lon"], -37.1)
        output = "\n".join(logs.output)
        self.assertIn("event=cache_expired", output)
        self.assertIn("event=provider_call", output)


if __name__ == "__main__":
    unittest.main()

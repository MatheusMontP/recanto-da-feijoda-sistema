import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.utils.google_maps import get_google_maps_distance_async


class GoogleMapsDistanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_distance_awaits_geocoder_and_calculates_distance(self):
        response = Mock()
        response.json.return_value = {"code": "Ok", "routes": [{"distance": 10000}]}

        async def fake_geocode(address):
            coords = {
                "Rua Origem": {"lat": -10.0, "lon": -37.0},
                "Destino": {"lat": -10.1, "lon": -37.1},
            }
            return coords[address]

        with (
            patch("app.utils.google_maps.geocode_address", new=AsyncMock(side_effect=fake_geocode)) as geocoder,
            patch("app.utils.google_maps.requests.get", return_value=response),
        ):
            distance = await get_google_maps_distance_async("Rua Origem", ["Destino"])

        self.assertEqual(distance, 10.3)
        self.assertEqual(geocoder.await_count, 2)

    async def test_osrm_log_does_not_expose_coordinates(self):
        response = Mock()
        response.json.return_value = {"code": "Ok", "routes": [{"distance": 10000}]}

        async def fake_geocode(address):
            return {"lat": -10.123456, "lon": -37.654321}

        with (
            self.assertLogs("lucromaximo", level="INFO") as logs,
            patch("app.utils.google_maps.geocode_address", new=AsyncMock(side_effect=fake_geocode)),
            patch("app.utils.google_maps.requests.get", return_value=response),
        ):
            await get_google_maps_distance_async("Origem", ["Destino"])

        output = "\n".join(logs.output)
        self.assertIn("Calculando rota OSRM para 2 pontos.", output)
        self.assertNotIn("-37.654321", output)
        self.assertNotIn("-10.123456", output)


if __name__ == "__main__":
    unittest.main()

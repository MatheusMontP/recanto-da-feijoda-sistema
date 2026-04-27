import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.api.endpoints import delivery
from app.models.schemas import RouteRequest


class DeliveryEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_optimize_route_awaits_distance_matrix_and_returns_route(self):
        async def fake_geocode_address(address):
            coords = {
                "Rua A": {"lat": -10.0, "lon": -37.0, "weak": False},
                "Rua B": {"lat": -10.1, "lon": -37.1, "weak": False},
            }
            return coords[address]

        async def fake_build_distance_matrix(origin, nodes):
            self.assertEqual(len(nodes), 2)
            return (
                [[0, 60, 120], [60, 0, 90], [120, 90, 0]],
                [[0, 1, 2], [1, 0, 1], [2, 1, 0]],
            )

        original_geocode = delivery.geocode_address
        original_build_matrix = delivery.build_distance_matrix
        delivery.geocode_address = fake_geocode_address
        delivery.build_distance_matrix = fake_build_distance_matrix
        try:
            req = RouteRequest(
                orders=[
                    {"address": "Rua A", "amount": 1},
                    {"address": "Rua B", "amount": 2},
                ],
                return_to_origin=True,
            )

            response = await delivery.optimize_route_endpoint(req)

            self.assertEqual(response.summary.total_stops, 2)
            self.assertEqual(response.summary.total_amount, 3)
            self.assertEqual(response.optimized.distance_km, 4)
            self.assertCountEqual([node.address for node in response.optimized.route], ["Rua A", "Rua B"])
        finally:
            delivery.geocode_address = original_geocode
            delivery.build_distance_matrix = original_build_matrix

    async def test_optimize_route_consolidates_duplicate_addresses(self):
        async def fake_geocode_address(address):
            return {"lat": -10.0, "lon": -37.0, "weak": False}

        async def fake_build_distance_matrix(origin, nodes):
            self.assertEqual(len(nodes), 1)
            return ([[0, 60], [60, 0]], [[0, 1], [1, 0]])

        original_geocode = delivery.geocode_address
        original_build_matrix = delivery.build_distance_matrix
        delivery.geocode_address = fake_geocode_address
        delivery.build_distance_matrix = fake_build_distance_matrix
        try:
            req = RouteRequest(
                orders=[
                    {"address": "Rua A", "amount": 1, "complement": "Casa 1"},
                    {"address": " rua a ", "amount": 2, "complement": "Casa 2"},
                ]
            )

            response = await delivery.optimize_route_endpoint(req)

            self.assertEqual(response.summary.total_stops, 1)
            self.assertEqual(response.summary.total_amount, 3)
            self.assertEqual(response.optimized.route[0].amount, 3)
            self.assertIn("Casa 1", response.optimized.route[0].complement)
            self.assertIn("Casa 2", response.optimized.route[0].complement)
        finally:
            delivery.geocode_address = original_geocode
            delivery.build_distance_matrix = original_build_matrix


class RouteRequestSchemaTests(unittest.TestCase):
    def test_normalizes_address_whitespace(self):
        req = RouteRequest(orders=[{"address": "  Rua   A,  123  ", "amount": 1}])

        self.assertEqual(req.orders[0].address, "Rua A, 123")

    def test_rejects_address_with_html(self):
        with self.assertRaises(ValueError):
            RouteRequest(orders=[{"address": "<img src=x onerror=alert(1)>", "amount": 1}])

    def test_rejects_address_with_control_characters(self):
        with self.assertRaises(ValueError):
            RouteRequest(orders=[{"address": "Rua A\x00", "amount": 1}])

    def test_rejects_invalid_optimization_mode(self):
        with self.assertRaises(ValueError):
            RouteRequest(orders=[{"address": "Rua A", "amount": 1}], optimize_for="fastest")

    def test_rejects_more_than_configured_stop_limit(self):
        orders = [{"address": f"Rua {i}", "amount": 1} for i in range(13)]

        with self.assertRaises(ValueError):
            RouteRequest(orders=orders)


if __name__ == "__main__":
    unittest.main()

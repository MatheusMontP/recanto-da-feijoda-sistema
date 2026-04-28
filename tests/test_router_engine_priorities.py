import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.services.geocoder import _fallback_by_neighborhood, _weak_result_matches_cep
from app.services.router_engine import (
    _address_has_neighborhood,
    _origin_priority_multiplier,
    _same_known_neighborhood,
    _select_secondary_priority_neighborhood,
    optimize_route_localized,
)


ORIGIN = (-10.97075, -37.06333)


class RouterPriorityTests(unittest.TestCase):
    def test_farolandia_always_gets_strongest_origin_bonus(self):
        self.assertEqual(_origin_priority_multiplier("Rua X, Farolandia, Aracaju", "atalaia"), 0.1)

    def test_augusto_franco_no_longer_gets_primary_origin_bonus(self):
        self.assertEqual(_origin_priority_multiplier("Rua Y, Augusto Franco, Aracaju", "atalaia"), 1.0)

    def test_secondary_priority_uses_selected_neighborhood_only(self):
        self.assertEqual(_origin_priority_multiplier("Av. Santos Dumont, Atalaia", "atalaia"), 0.25)
        self.assertEqual(_origin_priority_multiplier("Av. X, Aeroporto", "atalaia"), 1.0)

    def test_selects_secondary_neighborhood_with_more_deliveries(self):
        nodes = [
            {"address": "Rua A, Atalaia", "lat": -10.99, "lon": -37.04},
            {"address": "Rua B, Coroa do Meio", "lat": -10.96, "lon": -37.04},
            {"address": "Rua C, Coroa do Meio", "lat": -10.961, "lon": -37.041},
        ]

        self.assertEqual(_select_secondary_priority_neighborhood(ORIGIN, nodes), "coroa do meio")

    def test_selects_nearest_secondary_neighborhood_when_counts_tie(self):
        nodes = [
            {"address": "Rua A, Atalaia", "lat": -11.02, "lon": -37.02},
            {"address": "Rua B, Aeroporto", "lat": -10.97, "lon": -37.055},
        ]

        self.assertEqual(_select_secondary_priority_neighborhood(ORIGIN, nodes), "aeroporto")

    def test_neighborhood_matching_ignores_accents(self):
        self.assertTrue(_address_has_neighborhood("Rua X, Sao Conrado", "sao conrado"))
        self.assertTrue(_address_has_neighborhood("Rua Y, Farolandia", "farolandia"))

    def test_cluster_matching_includes_secondary_neighborhoods(self):
        self.assertTrue(_same_known_neighborhood("Rua A, Sao Conrado", "Rua B, Sao Conrado"))
        self.assertTrue(_same_known_neighborhood("Rua A, Coroa do Meio", "Rua B, Coroa do Meio"))
        self.assertFalse(_same_known_neighborhood("Rua A, Atalaia", "Rua B, Aeroporto"))

    def test_localized_route_prefers_next_stop_near_current_position(self):
        matrix = [
            [0.0, 1.0, 9.0, 10.0],
            [1.0, 0.0, 1.0, 8.0],
            [9.0, 1.0, 0.0, 7.0],
            [10.0, 8.0, 7.0, 0.0],
        ]

        self.assertEqual(optimize_route_localized(matrix, 3), [1, 2, 3])

    def test_localized_route_order_does_not_change_when_returning_to_origin(self):
        matrix = [
            [0.0, 1.0, 2.0, 3.0],
            [1.0, 0.0, 1.0, 9.0],
            [2.0, 1.0, 0.0, 1.0],
            [3.0, 9.0, 1.0, 0.0],
        ]

        self.assertEqual(
            optimize_route_localized(matrix, 3, return_to_origin=True),
            optimize_route_localized(matrix, 3, return_to_origin=False),
        )

    def test_weak_geocode_requires_matching_cep(self):
        self.assertTrue(_weak_result_matches_cep("Rua A, 49020-010", "Rua A, Aracaju, 49020-010"))
        self.assertFalse(_weak_result_matches_cep("Rua A, 49020-010", "Rua B, Aracaju, 49075-170"))

    def test_geocoder_falls_back_to_neighborhood_coordinates(self):
        fallback = _fallback_by_neighborhood("Rua Trinta e Um de Marco, 236 - Ponto Novo, Aracaju")

        self.assertIsNotNone(fallback)
        self.assertEqual(fallback["type"], "neighborhood_fallback")
        self.assertTrue(fallback["weak"])


if __name__ == "__main__":
    unittest.main()

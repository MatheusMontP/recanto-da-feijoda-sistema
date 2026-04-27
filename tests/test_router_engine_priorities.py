import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.services.router_engine import (
    _address_has_neighborhood,
    _origin_priority_multiplier,
    _same_known_neighborhood,
    _select_secondary_priority_neighborhood,
)


ORIGIN = (-10.97075, -37.06333)


class RouterPriorityTests(unittest.TestCase):
    def test_primary_priority_neighborhoods_always_get_strongest_origin_bonus(self):
        self.assertEqual(_origin_priority_multiplier("Rua X, Farolândia, Aracaju", "atalaia"), 0.1)
        self.assertEqual(_origin_priority_multiplier("Rua Y, Augusto Franco, Aracaju", "atalaia"), 0.1)

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
        self.assertTrue(_address_has_neighborhood("Rua X, São Conrado", "sao conrado"))
        self.assertTrue(_address_has_neighborhood("Rua Y, Farolândia", "farolandia"))

    def test_cluster_matching_includes_secondary_neighborhoods(self):
        self.assertTrue(_same_known_neighborhood("Rua A, São Conrado", "Rua B, Sao Conrado"))
        self.assertTrue(_same_known_neighborhood("Rua A, Coroa do Meio", "Rua B, Coroa do Meio"))
        self.assertFalse(_same_known_neighborhood("Rua A, Atalaia", "Rua B, Aeroporto"))


if __name__ == "__main__":
    unittest.main()

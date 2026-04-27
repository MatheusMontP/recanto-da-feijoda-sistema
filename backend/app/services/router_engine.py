import itertools
import logging

import aiohttp

from ..utils.geo import _strip_accents, haversine

logger = logging.getLogger("lucromaximo")

PRIMARY_PRIORITY_NEIGHBORHOODS = ("farolandia", "augusto franco")
SECONDARY_PRIORITY_NEIGHBORHOODS = ("atalaia", "coroa do meio", "sao conrado", "aeroporto")
CLUSTER_NEIGHBORHOODS = (
    "santa maria",
    "atalaia",
    "aruana",
    "aeroporto",
    "farolandia",
    "coroa do meio",
    "jardins",
    "augusto franco",
    "sao conrado",
)


def _normalized_address(address: str) -> str:
    return _strip_accents(address or "").lower()


def _address_has_neighborhood(address: str, neighborhood: str) -> bool:
    return neighborhood in _normalized_address(address)


def _select_secondary_priority_neighborhood(origin_coords: tuple[float, float], nodes: list[dict]) -> str | None:
    candidates = []

    for neighborhood in SECONDARY_PRIORITY_NEIGHBORHOODS:
        matching_nodes = [
            node for node in nodes
            if _address_has_neighborhood(node.get("address", ""), neighborhood)
        ]
        if not matching_nodes:
            continue

        nearest_distance = min(
            haversine(origin_coords[0], origin_coords[1], node["lat"], node["lon"])
            for node in matching_nodes
        )
        candidates.append((len(matching_nodes), -nearest_distance, neighborhood))

    if not candidates:
        return None

    # Mais entregas vence; em empate, o bairro mais perto da origem vence.
    return max(candidates)[2]


def _origin_priority_multiplier(address: str, secondary_priority_neighborhood: str | None) -> float:
    if any(_address_has_neighborhood(address, neighborhood) for neighborhood in PRIMARY_PRIORITY_NEIGHBORHOODS):
        return 0.1

    if secondary_priority_neighborhood and _address_has_neighborhood(address, secondary_priority_neighborhood):
        return 0.25

    return 1.0


def _same_known_neighborhood(address_a: str, address_b: str) -> bool:
    return any(
        _address_has_neighborhood(address_a, neighborhood)
        and _address_has_neighborhood(address_b, neighborhood)
        for neighborhood in CLUSTER_NEIGHBORHOODS
    )


async def build_distance_matrix(origin_coords: tuple[float, float], nodes: list[dict]) -> tuple[list[list[float]], list[list[float]]]:
    """Gera matrizes de tempo e distância usando a API pública do OSRM."""
    all_coords = [origin_coords] + [(n["lat"], n["lon"]) for n in nodes]
    secondary_priority_neighborhood = _select_secondary_priority_neighborhood(origin_coords, nodes)

    try:
        coords_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in all_coords])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration,distance"

        headers = {"User-Agent": "LucroMaximo_Logistics/1.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    raise ValueError(f"OSRM respondeu status {resp.status}")
                data = await resp.json()

                if data.get("code") == "Ok" and "distances" in data and "durations" in data:
                    dist_matrix = []
                    dur_matrix = []
                    n = len(all_coords)

                    for i in range(n):
                        row_dist = []
                        row_dur = []
                        for j in range(n):
                            val_dist = data["distances"][i][j]
                            val_dur = data["durations"][i][j]

                            coord_i = all_coords[i]
                            coord_j = all_coords[j]
                            h_dist = haversine(coord_i[0], coord_i[1], coord_j[0], coord_j[1])

                            osrm_dist_km = (val_dist / 1000.0) if val_dist is not None else float("inf")

                            if osrm_dist_km == float("inf") or osrm_dist_km > (h_dist * 3.0):
                                fallback_dist = h_dist * 1.3
                                osrm_dist_km = fallback_dist
                                val_dur = (fallback_dist / 25.0) * 3600.0

                            # O viés de prioridade só vale na primeira saída da origem.
                            if i == 0 and j > 0:
                                multiplier = _origin_priority_multiplier(
                                    nodes[j - 1]["address"],
                                    secondary_priority_neighborhood,
                                )
                                osrm_dist_km *= multiplier
                                val_dur *= multiplier

                            # Depois da primeira escolha, o algoritmo segue normal, com cluster de bairro.
                            if i > 0 and j > 0 and i != j:
                                if _same_known_neighborhood(nodes[i - 1]["address"], nodes[j - 1]["address"]):
                                    osrm_dist_km *= 0.1
                                    val_dur *= 0.1

                            row_dist.append(osrm_dist_km)
                            row_dur.append(val_dur if val_dur is not None else float("inf"))
                        dist_matrix.append(row_dist)
                        dur_matrix.append(row_dur)
                    return dur_matrix, dist_matrix

                raise ValueError("Dados incompletos na resposta do OSRM.")
    except Exception as exc:
        logger.error("Erro OSRM: %s", exc)
        n = len(all_coords)
        dist_matrix = [
            [
                haversine(all_coords[i][0], all_coords[i][1], all_coords[j][0], all_coords[j][1]) * 1.3
                for j in range(n)
            ]
            for i in range(n)
        ]
        dur_matrix = [[(dist_matrix[i][j] / 20.0) * 3600.0 for j in range(n)] for i in range(n)]
        return dur_matrix, dist_matrix


def compute_route_distance(matrix: list[list[float]], route_indices: list[int], return_to_origin: bool = True) -> float:
    """Soma as distâncias usando a matriz calculada."""
    total = 0.0
    current = 0
    for idx in route_indices:
        total += matrix[current][idx]
        current = idx
    if return_to_origin and route_indices:
        total += matrix[current][0]
    return total


def optimize_route_exact(matrix: list[list[float]], num_nodes: int, return_to_origin: bool = True) -> list[int]:
    """Implementação Held-Karp para TSP exato."""
    n = num_nodes + 1
    memo = {}
    for i in range(1, n):
        memo[(1 << i, i)] = (matrix[0][i], 0)
    for r in range(2, n):
        for subset in itertools.combinations(range(1, n), r):
            S = 0
            for v in subset:
                S |= (1 << v)
            for k in subset:
                S_prev = S ^ (1 << k)
                min_cost = float("inf")
                min_prev = None
                for m in subset:
                    if m == k:
                        continue
                    cost = memo[(S_prev, m)][0] + matrix[m][k]
                    if cost < min_cost:
                        min_cost = cost
                        min_prev = m
                memo[(S, k)] = (min_cost, min_prev)
    S_full = (1 << n) - 2
    min_cost = float("inf")
    last_node = None
    if return_to_origin:
        for k in range(1, n):
            cost = memo[(S_full, k)][0] + matrix[k][0]
            if cost < min_cost:
                min_cost = cost
                last_node = k
    else:
        for k in range(1, n):
            cost = memo[(S_full, k)][0]
            if cost < min_cost:
                min_cost = cost
                last_node = k
    route = []
    curr_node = last_node
    curr_S = S_full
    while curr_node != 0:
        route.append(curr_node)
        prev_node = memo[(curr_S, curr_node)][1]
        curr_S = curr_S ^ (1 << curr_node)
        curr_node = prev_node
    return list(reversed(route))

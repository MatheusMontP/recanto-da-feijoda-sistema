import aiohttp
import asyncio
import json
import logging
import itertools
from fastapi import HTTPException
from ..utils.geo import haversine

logger = logging.getLogger("lucromaximo")

async def build_distance_matrix(origin_coords: tuple[float, float], nodes: list[dict]) -> tuple[list[list[float]], list[list[float]]]:
    """Gera matrizes de tempo e distância usando exclusivamente a API pública do OSRM de forma assíncrona."""
    all_coords = [origin_coords] + [(n["lat"], n["lon"]) for n in nodes]
    
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
                            
                            # Fallback Logic
                            coord_i = all_coords[i]
                            coord_j = all_coords[j]
                            h_dist = haversine(coord_i[0], coord_i[1], coord_j[0], coord_j[1])
                            
                            osrm_dist_km = (val_dist / 1000.0) if val_dist is not None else float('inf')
                            
                            # SANITY CHECK: Se o OSRM falhar ou der rota absurda, usa haversine * 1.3
                            if osrm_dist_km == float('inf') or osrm_dist_km > (h_dist * 3.0):
                                fallback_dist = h_dist * 1.3
                                osrm_dist_km = fallback_dist
                                val_dur = (fallback_dist / 25.0) * 3600.0

                            # BÔNUS DE PRIORIDADE E VIZINHANÇA
                            priority_neighborhoods = ["farolandia", "augusto franco", "farolândia"]
                            all_neighborhoods = ["santa maria", "atalaia", "aruana", "aeroporto", "farolandia", "coroa do meio", "jardins", "augusto franco", "farolândia"]
                            
                            # 1. Prioridade a partir da Origem (index 0)
                            if i == 0 and j > 0:
                                addr_j = nodes[j-1]["address"].lower()
                                for b in priority_neighborhoods:
                                    if b in addr_j:
                                        # Reduz drasticamente o custo inicial para forçar o algoritmo a começar por aqui
                                        osrm_dist_km *= 0.1
                                        val_dur *= 0.1
                                        break
                            
                            # 2. Clustering (Vizinhos no mesmo bairro)
                            if i > 0 and j > 0 and i != j:
                                addr_i = nodes[i-1]["address"].lower()
                                addr_j = nodes[j-1]["address"].lower()
                                for b in all_neighborhoods:
                                    if b in addr_i and b in addr_j:
                                        osrm_dist_km *= 0.1
                                        val_dur *= 0.1
                                        break
                                
                            row_dist.append(osrm_dist_km)
                            row_dur.append(val_dur if val_dur is not None else float('inf'))
                        dist_matrix.append(row_dist)
                        dur_matrix.append(row_dur)
                    return dur_matrix, dist_matrix
                else:
                    raise ValueError("Dados incompletos na resposta do OSRM.")
    except Exception as exc:
        logger.error(f"Erro OSRM: {exc}")
        # Se falhar o OSRM, montamos uma matriz Haversine básica para não deixar o usuário na mão
        n = len(all_coords)
        dist_matrix = [[haversine(all_coords[i][0], all_coords[i][1], all_coords[j][0], all_coords[j][1]) * 1.3 for j in range(n)] for i in range(n)]
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
            for v in subset: S |= (1 << v)
            for k in subset:
                S_prev = S ^ (1 << k)
                min_cost = float('inf')
                min_prev = None
                for m in subset:
                    if m == k: continue
                    cost = memo[(S_prev, m)][0] + matrix[m][k]
                    if cost < min_cost:
                        min_cost = cost
                        min_prev = m
                memo[(S, k)] = (min_cost, min_prev)
    S_full = (1 << n) - 2
    min_cost = float('inf')
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

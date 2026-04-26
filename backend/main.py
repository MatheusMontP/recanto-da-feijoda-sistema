"""
LucroMáximo Logistics — Backend API
Sistema de Roteirização de Blocos para entregas de feijoada.

Arquitetura:
  - FastAPI serve a API REST e o frontend estático
  - Geocodificação via geopy/Nominatim com fallback inteligente
  - Otimização de rota via algoritmo Nearest Neighbor (Vizinho Mais Próximo)
  - Distâncias calculadas pela fórmula de Haversine
"""

import math
import os
import re
import time
import logging
import unicodedata
import urllib.request
import json
from urllib.error import URLError

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import List
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lucromaximo")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
RESTAURANTE_NOME = "Recanto da Feijoada"
RESTAURANTE_ENDERECO = "R. Brasílio Martinho Vale, 46 - Farolândia, Aracaju - SE"
# Coordenadas fixas da origem (R. Brasílio Martinho Vale, 46 — Farolândia, Aracaju)
RESTAURANTE_COORDS = (-10.97075, -37.06333)

MAX_PARADAS_POR_BLOCO = 12

# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(
    title="LucroMáximo Logistics",
    description="API de roteirização de entregas com otimização geográfica.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Geocodificação
# ---------------------------------------------------------------------------
geolocator = Nominatim(user_agent="lucromaximo_logistics_v1")

# Cache em memória para evitar chamadas repetidas ao Nominatim
_geocode_cache: dict[str, tuple[float, float] | None] = {}


def _strip_accents(text: str) -> str:
    """Remove acentos de uma string (ex: Farolândia -> Farolandia)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _nominatim_query(query: str) -> tuple[float, float] | None:
    """Faz uma única chamada ao Nominatim com rate-limit de 1.2s."""
    normalized = query.strip()
    if not normalized:
        return None

    if normalized in _geocode_cache:
        return _geocode_cache[normalized]

    try:
        location = geolocator.geocode(normalized, timeout=10)
        time.sleep(1.2)  # Respeita policy do Nominatim (max 1 req/s)
        if location:
            coords = (location.latitude, location.longitude)
            _geocode_cache[normalized] = coords
            logger.info("Geocodificado: '%s' -> %s", normalized, coords)
            return coords
        logger.warning("Nominatim não encontrou: '%s'", normalized)
        _geocode_cache[normalized] = None
        return None
    except Exception as exc:
        logger.error("Erro Nominatim para '%s': %s", normalized, exc)
        return None


def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Tenta geocodificar um endereço brasileiro com 5 estratégias de fallback:
      1. Endereço completo (como digitado)
      2. Endereço sem acentos
      3. Remove números de casa
      4. Sem números e sem acentos
      5. Apenas Bairro + Cidade (últimos 2 termos)
    """
    # Garante que a busca sempre aponte para Aracaju (fallback de segurança)
    if "aracaju" not in address.lower():
        address = f"{address}, Aracaju"

    # Correção de Bairros (Aliases para o OpenStreetMap em Aracaju)
    # O Nominatim frequentemente registra bairros numéricos apenas com os números
    address = re.sub(r'\btreze de julho\b', '13 de julho', address, flags=re.IGNORECASE)
    address = re.sub(r'\bdezoito do forte\b', '18 do forte', address, flags=re.IGNORECASE)

    # Tentativa 1: Exato
    coords = _nominatim_query(address)
    if coords:
        return coords

    # Tentativa 2: Sem acentos
    no_accent = _strip_accents(address)
    if no_accent != address:
        coords = _nominatim_query(no_accent)
        if coords:
            return coords

    # Tentativa 3-5: Manipulação de partes
    parts = [p.strip() for p in address.split(",")]
    if len(parts) > 1:
        filtered = [p for p in parts if not re.match(r"^(s/n|sn|\d+.*)$", p.strip().lower())]
        if filtered and len(filtered) < len(parts):
            # Tentativa 3: Sem números
            coords = _nominatim_query(", ".join(filtered))
            if coords:
                return coords
            # Tentativa 4: Sem números + sem acentos
            coords = _nominatim_query(_strip_accents(", ".join(filtered)))
            if coords:
                return coords

        # Tentativa 5: Bairro + Cidade
        tail = filtered[-2:] if len(filtered) >= 2 else parts[-2:]
        coords = _nominatim_query(", ".join(tail))
        if coords:
            return coords
        coords = _nominatim_query(_strip_accents(", ".join(tail)))
        if coords:
            return coords

    return None


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula a distância em km entre dois pontos na superfície terrestre."""
    R = 6371.0  # Raio da Terra em km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Algoritmos de Rota (Cálculo de Matriz e Otimização)
# ---------------------------------------------------------------------------

def build_distance_matrix(origin_coords: tuple[float, float], nodes: list[dict]) -> tuple[list[list[float]], list[list[float]]]:
    """Gera matrizes de tempo e distância usando exclusivamente a API pública do OSRM."""
    all_coords = [origin_coords] + [(n["lat"], n["lon"]) for n in nodes]
    
    try:
        coords_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in all_coords])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration,distance"
        
        import urllib.request
        import json
        req = urllib.request.Request(url, headers={"User-Agent": "LucroMaximo_Logistics/1.0"})
        # Timeout aumentado para dar margem à API pública
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get("code") == "Ok" and "distances" in data and "durations" in data:
                logger.info("Matriz OSRM construída com sucesso.")
                
                # Exibe log bruto para conferência de escala (como pedido)
                if len(data["distances"]) > 1 and len(data["distances"][0]) > 1:
                    raw_val = data["distances"][0][1]
                    logger.info("--- DEBUG OSRM --- Valor bruto de 0 -> 1: %s (metros). Convertido: %.3f (km)", raw_val, raw_val / 1000.0)

                dist_matrix = []
                dur_matrix = []
                for row in data["distances"]:
                    # OSRM dá em metros. Dividimos por 1000 para converter para km reais de asfalto.
                    dist_matrix.append([(val / 1000.0) if val is not None else float('inf') for val in row])
                for row in data["durations"]:
                    # OSRM dá em segundos. Mantemos em segundos para a otimização.
                    dur_matrix.append([val if val is not None else float('inf') for val in row])
                return dur_matrix, dist_matrix
            else:
                raise ValueError("Resposta OSRM inválida ou sem distâncias/durações.")
    except Exception as exc:
        logger.error("OSRM indisponível ou erro na resposta. Erro: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Serviço de cálculo de rotas (OSRM) temporariamente indisponível. Tente novamente em alguns segundos."
        )


def compute_route_distance(matrix: list[list[float]], route_indices: list[int]) -> float:
    """Soma as distâncias usando a matriz real. Indices partem da origem (0)."""
    total = 0.0
    current = 0  # Origem
    for idx in route_indices:
        total += matrix[current][idx]
        current = idx
    
    # Adiciona a distância de retorno (do último ponto de entrega de volta ao restaurante)
    if route_indices:
        total += matrix[current][0]
        
    return total


def optimize_route_exact(matrix: list[list[float]], num_nodes: int) -> list[int]:
    """
    Descobre a melhor rota matematicamente possível usando Programação Dinâmica Exata (Held-Karp).
    Como o limite é de 12 paradas (13 nós com a origem), esse algoritmo roda em milissegundos
    e garante o caminho absoluto mais curto, eliminando problemas de mínimos locais.
    """
    import itertools
    n = num_nodes + 1  # Inclui a origem (0)
    
    # memo[(S, last_node)] = (cost, previous_node)
    memo = {}
    
    # Inicialização (origem -> nó i)
    for i in range(1, n):
        memo[(1 << i, i)] = (matrix[0][i], 0)
        
    # Preenchimento (subconjuntos de tamanho 2 até n-1)
    for r in range(2, n):
        for subset in itertools.combinations(range(1, n), r):
            S = 0
            for v in subset:
                S |= (1 << v)
                
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
                
    # Fechar o ciclo (voltar ao 0)
    S_full = (1 << n) - 2 # Todos os bits de 1 a n-1 setados
    min_cost = float('inf')
    last_node = None
    
    for k in range(1, n):
        cost = memo[(S_full, k)][0] + matrix[k][0]
        if cost < min_cost:
            min_cost = cost
            last_node = k
            
    # Reconstruir o melhor caminho
    route = []
    curr_node = last_node
    curr_S = S_full
    
    while curr_node != 0:
        route.append(curr_node)
        prev_node = memo[(curr_S, curr_node)][1]
        curr_S = curr_S ^ (1 << curr_node)
        curr_node = prev_node
        
    # O caminho é reconstruído de trás para frente, então revertemos
    return list(reversed(route))


# ---------------------------------------------------------------------------
# Schemas Pydantic
# ---------------------------------------------------------------------------
class OrderItem(BaseModel):
    address: str = Field(..., min_length=3, description="Endereço de entrega")
    amount: int = Field(..., ge=1, description="Quantidade de feijoadas")
    complement: str = Field(default="", description="Complemento ou Ponto de Ref.")


class RouteRequest(BaseModel):
    orders: List[OrderItem] = Field(..., min_length=1, max_length=MAX_PARADAS_POR_BLOCO)


class RouteNode(BaseModel):
    address: str
    amount: int
    complement: str
    lat: float
    lon: float


class RouteSummary(BaseModel):
    total_stops: int
    total_amount: int


class RouteResult(BaseModel):
    distance_km: float
    route: List[RouteNode]


class GeoError(BaseModel):
    index: int
    address: str
    message: str


class RouteResponse(BaseModel):
    summary: RouteSummary
    original: RouteResult
    optimized: RouteResult
    errors: List[GeoError] = []





# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/optimize_route", response_model=RouteResponse)
def optimize_route(req: RouteRequest):
    """Recebe pedidos, consolida duplicatas, geocodifica e otimiza a rota."""
    origin = RESTAURANTE_COORDS

    # 1. Consolidar pedidos com mesmo endereço
    consolidated: dict[str, dict] = {}
    for idx, order in enumerate(req.orders):
        key = _strip_accents(order.address.strip().lower())
        if key in consolidated:
            consolidated[key]["amount"] += order.amount
            if order.complement:
                if consolidated[key]["complement"]:
                    if order.complement.lower() not in consolidated[key]["complement"].lower():
                        consolidated[key]["complement"] += f" | {order.complement}"
                else:
                    consolidated[key]["complement"] = order.complement
        else:
            consolidated[key] = {
                "original_idx": idx,
                "address": order.address.strip(),
                "amount": order.amount,
                "complement": order.complement.strip() if order.complement else "",
            }

    unique_orders = sorted(consolidated.values(), key=lambda x: x["original_idx"])

    # 2. Geocodificar cada endereço — coleta erros individuais
    nodes: list[dict] = []
    geo_errors: list[dict] = []
    total_amount = 0

    for entry in unique_orders:
        coords = geocode_address(entry["address"])
        if not coords:
            geo_errors.append({
                "index": entry["original_idx"],
                "address": entry["address"],
                "message": "Não encontrado no mapa. Dica: Verifique a digitação e tente usar o formato 'Rua X, 123, Bairro, Aracaju'.",
            })
            continue

        # Regra de negócio: raio máximo de 50km a partir do restaurante
        dist_from_origin = haversine(origin[0], origin[1], coords[0], coords[1])
        if dist_from_origin > 25.0:
            geo_errors.append({
                "index": entry["original_idx"],
                "address": entry["address"],
                "message": f"Endereço '{entry['address']}' está a {dist_from_origin:.0f}km do restaurante (máx. 25km). Verifique se o endereço está correto.",
            })
            logger.warning("Endereço fora do raio de entrega (%.1fkm): '%s'", dist_from_origin, entry["address"])
            continue

        nodes.append({
            "address": entry["address"],
            "amount": entry["amount"],
            "complement": entry["complement"],
            "lat": coords[0],
            "lon": coords[1],
        })
        total_amount += entry["amount"]

    # Se NENHUM endereço foi encontrado, erro fatal
    if not nodes:
        raise HTTPException(
            status_code=400,
            detail="Nenhum endereço pôde ser localizado. Verifique os dados e tente novamente.",
        )

    # 3. Gerar Matrizes de Tempo (para otimizar) e Distância (para exibir)
    dur_matrix, dist_matrix = build_distance_matrix(origin, nodes)

    # 4. Rota original (ordem de inserção)
    original_indices = list(range(1, len(nodes) + 1))
    original_dist = compute_route_distance(dist_matrix, original_indices)

    # 5. Rota matematicamente ótima (Held-Karp Exact TSP otimizando TEMPO)
    # Passamos a dur_matrix para que o algoritmo priorize vias expressas rápidas
    optimized_indices = optimize_route_exact(dur_matrix, len(nodes))
    optimized_dist = compute_route_distance(dist_matrix, optimized_indices)

    # 6. Fator de Calibração Final (Aproximação Waze/Google Maps)
    # Reduz em 25% o número cru do OSRM para abater os retornos falsos e as rotas fantasmas geradas 
    # por imprecisão de pinos nos bairros, aproximando o valor do que o motoboy realmente dirige.
    calibrated_original = original_dist * 0.75
    calibrated_optimized = optimized_dist * 0.75

    # Mapear chaves para os nós reais
    optimized_nodes = [nodes[i - 1] for i in optimized_indices]

    return RouteResponse(
        summary=RouteSummary(total_stops=len(nodes), total_amount=total_amount),
        original=RouteResult(distance_km=round(calibrated_original, 2), route=nodes),
        optimized=RouteResult(distance_km=round(calibrated_optimized, 2), route=optimized_nodes),
        errors=[GeoError(**e) for e in geo_errors],
    )


# ---------------------------------------------------------------------------
# Servir Frontend estático
# ---------------------------------------------------------------------------
_frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/app/")


# IMPORTANTE: mount de estáticos DEVE vir por último, após todas as rotas da API
app.mount("/app", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

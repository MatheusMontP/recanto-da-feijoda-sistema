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
RESTAURANTE_ENDERECO = "Farolândia, Aracaju"
# Coordenadas fixas da origem (Rua Martinho Brasilio Valle, 46 — Farolândia)
RESTAURANTE_COORDS = (-10.9746052, -37.063972)

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
def build_distance_matrix(origin_coords: tuple[float, float], nodes: list[dict]) -> list[list[float]]:
    """Gera matriz de distâncias (em km). Tenta usar OSRM (ruas reais), usa Haversine como fallback."""
    all_coords = [origin_coords] + [(n["lat"], n["lon"]) for n in nodes]
    
    # 1. Tentativa via OSRM (API Pública)
    try:
        # Padrão OSRM: longitude, latitude
        coords_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in all_coords])
        url = f"http://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=distance"
        
        req = urllib.request.Request(url, headers={"User-Agent": "LucroMaximo_Logistics/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            if data.get("code") == "Ok" and "distances" in data:
                logger.info("Matriz OSRM construída com sucesso (Ruas reais).")
                matrix = []
                for row in data["distances"]:
                    # Converte de metros para km
                    matrix.append([(val / 1000.0) if val is not None else float('inf') for val in row])
                return matrix
    except Exception as exc:
        logger.warning("OSRM indisponível ou falhou, ativando fallback Haversine. Erro: %s", exc)

    # 2. Fallback: Matemática em Linha Reta
    logger.info("Matriz Fallback Ativada (Haversine).")
    matrix = []
    for i in range(len(all_coords)):
        row = []
        for j in range(len(all_coords)):
            if i == j:
                row.append(0.0)
            else:
                row.append(haversine(all_coords[i][0], all_coords[i][1], all_coords[j][0], all_coords[j][1]))
        matrix.append(row)
    return matrix


def compute_route_distance(matrix: list[list[float]], route_indices: list[int]) -> float:
    """Soma as distâncias usando a matriz real. Indices partem da origem (0)."""
    total = 0.0
    current = 0  # Origem
    for idx in route_indices:
        total += matrix[current][idx]
        current = idx
    return total


def nearest_neighbor(matrix: list[list[float]], num_nodes: int) -> list[int]:
    """Descobre a melhor rota via Vizinho Mais Próximo consultando a matriz."""
    unvisited = list(range(1, num_nodes + 1))
    route = []
    current = 0
    
    while unvisited:
        nearest_idx = min(unvisited, key=lambda i: matrix[current][i])
        unvisited.remove(nearest_idx)
        route.append(nearest_idx)
        current = nearest_idx
        
    return route


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
                "message": f"Endereço não localizado: '{entry['address']}'. Tente 'Rua, Bairro, Cidade'.",
            })
            continue  # Pula, mas não aborta o bloco inteiro
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

    # 3. Gerar Matriz de Distâncias
    dist_matrix = build_distance_matrix(origin, nodes)

    # 4. Rota original (ordem de inserção)
    original_indices = list(range(1, len(nodes) + 1))
    original_dist = compute_route_distance(dist_matrix, original_indices)

    # 5. Rota otimizada (Nearest Neighbor)
    optimized_indices = nearest_neighbor(dist_matrix, len(nodes))
    optimized_dist = compute_route_distance(dist_matrix, optimized_indices)

    # Mapear chaves para os nós reais
    optimized_nodes = [nodes[i - 1] for i in optimized_indices]

    return RouteResponse(
        summary=RouteSummary(total_stops=len(nodes), total_amount=total_amount),
        original=RouteResult(distance_km=round(original_dist, 2), route=nodes),
        optimized=RouteResult(distance_km=round(optimized_dist, 2), route=optimized_nodes),
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

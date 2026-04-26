"""
LucroMáximo Logistics — Backend API v1.1
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
import json
import sqlite3
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

MAX_PARADAS_POR_BLOCO = 15
CACHE_DB = "geocache.db"

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

# Cache em memória e SQLite
_geocode_cache: dict[str, dict | None] = {}

def _strip_accents(text: str) -> str:
    """Remove acentos de uma string (ex: Farolândia -> Farolandia)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def init_db():
    try:
        conn = sqlite3.connect(CACHE_DB)
        conn.execute("CREATE TABLE IF NOT EXISTS geocache (query TEXT PRIMARY KEY, data TEXT)")
        conn.close()
    except Exception as e:
        logger.warning("Erro ao inicializar DB de cache: %s", e)

init_db()

def get_cached_geocode(query: str) -> tuple[dict | None, bool]:
    if query in _geocode_cache:
        return _geocode_cache[query], True
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.execute("SELECT data FROM geocache WHERE query = ?", (query,))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            _geocode_cache[query] = data
            return data, True # Encontrado no cache (mesmo se for None)
    except Exception as e:
        logger.warning("Erro ao ler cache: %s", e)
    return None, False

def set_cached_geocode(query: str, data: dict | None):
    _geocode_cache[query] = data
    try:
        conn = sqlite3.connect(CACHE_DB)
        # Garante que a tabela existe antes de inserir (caso o arquivo tenha sido deletado)
        conn.execute("CREATE TABLE IF NOT EXISTS geocache (query TEXT PRIMARY KEY, data TEXT)")
        conn.execute("INSERT OR REPLACE INTO geocache (query, data) VALUES (?, ?)", 
                     (query, json.dumps(data)))
        conn.commit()
        conn.close()
        conn.close()
    except Exception as e:
        logger.warning("Erro ao salvar cache: %s", e)

def _nominatim_query(query: str) -> dict | None:
    """Faz uma única chamada ao Nominatim com rate-limit e retorna dados completos."""
    normalized = query.strip().strip(",")
    if not normalized:
        return None

    cached_val, found = get_cached_geocode(normalized)
    if found:
        return cached_val

    try:
        # Força busca em Aracaju - SE, Brasil se não especificado
        search_query = normalized
        if "aracaju" not in search_query.lower():
            search_query += ", Aracaju - SE, Brasil"
            
        location = geolocator.geocode(search_query, timeout=10, addressdetails=True)
        time.sleep(1.2)  # Respeita policy do Nominatim
        
        if location:
            # Validação de Segurança: O resultado DEVE ser em Aracaju
            if "Aracaju" not in location.address:
                logger.warning("Resultado ignorado (fora de Aracaju): '%s'", location.address)
                return None

            res = {
                "lat": location.latitude,
                "lon": location.longitude,
                "importance": location.raw.get("importance", 0),
                "type": location.raw.get("type", "unknown"),
                "class": location.raw.get("class", "unknown"),
                "display_name": location.address,
                "address": location.raw.get("address", {})
            }
            set_cached_geocode(normalized, res)
            logger.info("Geocodificado: '%s' -> %s (%s)", normalized, (res["lat"], res["lon"]), res["type"])
            return res
            
        logger.warning("Nominatim não encontrou: '%s'", normalized)
        set_cached_geocode(normalized, None)
        return None
    except Exception as exc:
        logger.error("Erro Nominatim para '%s': %s", normalized, exc)
        return None

def geocode_address(address: str) -> dict | None:
    """
    Tenta geocodificar um endereço com fallbacks e sinalização de qualidade.
    Retorna dict com coords e flag 'weak'.
    """
    # Correção de Bairros
    # Padronização: transforma '-' em ',' para facilitar o split
    # Mas apenas se não estiver cercado por letras (para não quebrar nomes de ruas hifenizados)
    address = re.sub(r'(?<=\d)\s*-\s*(?=[a-zA-Z])', ', ', address)
    address = re.sub(r'(?<=[a-zA-Z])\s*-\s*(?=\d)', ', ', address)
    # Se sobrar algum ' - ' genérico, vira vírgula
    address = address.replace(" - ", ", ")
    
    # Remove CEP (XXXXX-XXX ou XXXXX,XXX ou XXXXX.XXX ou XXXXXXXX)
    address = re.sub(r'\b\d{5}[-,\.\s]?\d{3}\b', '', address)
    # Expansão de abreviações comuns
    address = re.sub(r'\bR\.\s+', 'Rua ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bAv\.\s+', 'Avenida ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bLot\.\s+', 'Loteamento ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bSen\.\s+', 'Senador ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bPref\.\s+', 'Prefeito ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bCel\.\s+', 'Coronel ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bDr\.\s+', 'Doutor ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bProf\.\s+', 'Professor ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bPça\.\s+', 'Praça ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bCond\.\s+', 'Condomínio ', address, flags=re.IGNORECASE)
    address = re.sub(r'\bRes\.\s+', 'Residencial ', address, flags=re.IGNORECASE)

    # Limpeza de vírgulas duplas e espaços extras
    address = re.sub(r',\s*,', ',', address)
    address = re.sub(r'\s+', ' ', address).strip().strip(",")

    # Nomes que costumam ser omitidos no mapa (Prefeito, Doutor, etc)
    # Se falhar com o nome completo, tentaremos sem esses títulos
    titles_to_strip = r'\b(prefeito|doutor|dr|senador|sen|coronel|cel|professor|prof)\b'

    # Tentativas
    strategies = [
        {"name": "full", "query": address},
        {"name": "no_accent", "query": _strip_accents(address)}
    ]
    
    # Se tem "Loteamento", tenta também sem a palavra "Loteamento"
    if "loteamento" in address.lower():
        clean_lot = re.sub(r'\bloteamento\b', '', address, flags=re.IGNORECASE).strip()
        strategies.append({"name": "no_lot", "query": clean_lot})
    
    # Se tem títulos, tenta também sem eles
    clean_titles = re.sub(titles_to_strip, '', address, flags=re.IGNORECASE).strip()
    if clean_titles != address:
        strategies.append({"name": "no_title", "query": clean_titles})
        strategies.append({"name": "no_title_accent", "query": _strip_accents(clean_titles)})
    
    parts = [p.strip() for p in address.split(",")]
    if len(parts) > 1:
        # Remove números da lista de partes para busca genérica
        filtered = [p for p in parts if not re.match(r"^(s/n|sn|\d+.*)$", p.strip().lower())]
        
        # Identifica Cidade e Estado (geralmente as últimas partes)
        # Se a última parte for 'SE' ou 'Sergipe', a penúltima é a cidade
        has_state = parts[-1].lower() in ["se", "sergipe"]
        city_idx = -2 if has_state and len(parts) >= 2 else -1
        city = parts[city_idx].strip()
        
        if filtered:
            strategies.append({"name": "no_number", "query": ", ".join(filtered)})
            strategies.append({"name": "no_number_accent", "query": _strip_accents(", ".join(filtered))})
        
        # Fallback: Apenas Rua + Cidade
        if len(parts) >= 2:
            street = parts[0].strip()
            # Se a rua tem um nome "curto" ou genérico, não arriscamos sem o bairro
            is_generic = re.match(r"^(rua|travessa|avenida|alameda|pça|praça|r|av)\s+([a-z]|[0-9]{1,2})$", street.lower())
            if not is_generic:
                strategies.insert(2, {"name": "street_city", "query": f"{street}, {city}", "is_weak": True})
                strategies.insert(3, {"name": "street_city_accent", "query": _strip_accents(f"{street}, {city}"), "is_weak": True})

        # Fallback genérico (Bairro + Cidade)
        # Bairro costuma ser a parte antes da Cidade
        nb_idx = city_idx - 1
        if abs(nb_idx) <= len(parts):
            neighborhood = parts[nb_idx].strip()
            if neighborhood.lower() not in ["aracaju", "se", "sergipe"]:
                strategies.append({"name": "neighborhood", "query": f"{neighborhood}, {city}", "is_weak": True})

    for s in strategies:
        res = _nominatim_query(s.get("query"))
        if res:
            res["weak"] = s.get("is_weak", False)
            
            # Validação Extra para Ruas Genéricas:
            # Se a rua for genérica (Rua C, Travessa 1), o bairro no resultado DEVE bater com o bairro pedido
            if len(parts) >= 2:
                street_name = parts[0].strip().lower()
                requested_nb = _strip_accents(parts[1].strip().lower())
                is_gen = re.match(r"^(rua|travessa|avenida|alameda|pça|praça)\s+([a-z]|[0-9]{1,2})$", street_name)
                
                if is_gen:
                    res_nb = _strip_accents(str(res.get("address", {}).get("suburb", "")).lower())
                    res_nb2 = _strip_accents(str(res.get("address", {}).get("neighbourhood", "")).lower())
                    if requested_nb not in res_nb and requested_nb not in res_nb2 and res_nb not in requested_nb:
                        logger.warning("Resultado descartado (Bairro não condiz com rua genérica): Pedido: %s, Obtido: %s/%s", requested_nb, res_nb, res_nb2)
                        continue # Tenta próxima estratégia (provavelmente vai cair no centro do bairro correto)

            # Adicional: se o Nominatim retornar algo como 'postcode' ou 'administrative' sem ser rua, marcar como fraco
            if res["type"] in ["administrative", "postcode", "suburb", "city"]:
                res["weak"] = True
            return res

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
                n = len(all_coords)
                
                for i in range(n):
                    row_dist = []
                    row_dur = []
                    for j in range(n):
                        val_dist = data["distances"][i][j]
                        val_dur = data["durations"][i][j]
                        
                        # Sanity Check: Comparar com Haversine
                        h_dist = haversine(all_coords[i][0], all_coords[i][1], all_coords[j][0], all_coords[j][1])
                        
                        # Fallback se OSRM for absurdo (> 3.5x Haversine ou None/inf)
                        # Multiplicador 1.3x para Haversine (estimativa urbana)
                        osrm_dist_km = (val_dist / 1000.0) if val_dist is not None else float('inf')
                        
                        is_suspect = False
                        if osrm_dist_km == float('inf') or (h_dist > 0.1 and osrm_dist_km > h_dist * 3.5):
                            is_suspect = True
                            fallback_dist = h_dist * 1.3  # Aproximação conservadora
                            logger.warning("Matriz Suspeita [%d->%d]: OSRM=%.2fkm, Haversine=%.2fkm. Aplicando fallback=%.2fkm", 
                                           i, j, osrm_dist_km, h_dist, fallback_dist)
                            osrm_dist_km = fallback_dist
                            # Estima duração baseada em 30km/h se falhar
                            val_dur = (fallback_dist / 30.0) * 3600.0
                            
                        row_dist.append(osrm_dist_km)
                        row_dur.append(val_dur if val_dur is not None else float('inf'))
                    dist_matrix.append(row_dist)
                    dur_matrix.append(row_dur)
                return dur_matrix, dist_matrix
            else:
                raise ValueError("Resposta OSRM inválida ou sem distâncias/durações.")
    except Exception as exc:
        logger.error("OSRM indisponível ou erro na resposta. Erro: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Serviço de cálculo de rotas (OSRM) temporariamente indisponível. Tente novamente em alguns segundos."
        )


def compute_route_distance(matrix: list[list[float]], route_indices: list[int], return_to_origin: bool = True) -> float:
    """Soma as distâncias usando a matriz real."""
    total = 0.0
    current = 0  # Origem
    for idx in route_indices:
        total += matrix[current][idx]
        current = idx
    
    if return_to_origin and route_indices:
        total += matrix[current][0]
        
    return total


def optimize_route_exact(matrix: list[list[float]], num_nodes: int, return_to_origin: bool = True) -> list[int]:
    """Held-Karp para TSP ou Caminho Aberto."""
    import itertools
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
        # Caminho aberto: qualquer um pode ser o último
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


# ---------------------------------------------------------------------------
# Schemas Pydantic
# ---------------------------------------------------------------------------
class OrderItem(BaseModel):
    address: str = Field(..., min_length=3, description="Endereço de entrega")
    amount: int = Field(..., ge=1, description="Quantidade de feijoadas")
    complement: str = Field(default="", description="Complemento ou Ponto de Ref.")


class RouteRequest(BaseModel):
    orders: List[OrderItem] = Field(..., min_length=1, max_length=MAX_PARADAS_POR_BLOCO)
    optimize_for: str = Field(default="distance", description="distance ou duration")
    return_to_origin: bool = Field(default=True, description="Volta ao restaurante?")


class RouteNode(BaseModel):
    address: str
    amount: int
    complement: str
    lat: float
    lon: float
    weak: bool = False


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
        res = geocode_address(entry["address"])
        if not res:
            geo_errors.append({
                "index": entry["original_idx"],
                "address": entry["address"],
                "message": "Não encontrado no mapa. Verifique a digitação.",
            })
            continue

        coords = (res["lat"], res["lon"])

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
            "lat": res["lat"],
            "lon": res["lon"],
            "weak": res.get("weak", False)
        })
        if res.get("weak"):
            logger.info("Geocode FRACO detectado para: %s", entry["address"])
            
        total_amount += entry["amount"]

    # Se NENHUM endereço foi encontrado, erro fatal
    if not nodes:
        raise HTTPException(
            status_code=400,
            detail="Nenhum endereço pôde ser localizado. Verifique os dados e tente novamente.",
        )

    # 3. Gerar Matrizes
    # OSRM para real, Fallback para suspeitos
    dur_matrix_osrm, dist_matrix_osrm = build_distance_matrix(origin, nodes)
    
    # 4. Escolher matriz de custo para otimização
    cost_matrix = dist_matrix_osrm if req.optimize_for == "distance" else dur_matrix_osrm

    # 5. Rota original
    original_indices = list(range(1, len(nodes) + 1))
    original_dist = compute_route_distance(dist_matrix_osrm, original_indices, req.return_to_origin)

    # 6. Rota matematicamente ótima
    optimized_indices = optimize_route_exact(cost_matrix, len(nodes), req.return_to_origin)
    optimized_dist = compute_route_distance(dist_matrix_osrm, optimized_indices, req.return_to_origin)

    # 7. Calibração e Nodes
    # Fator de Calibração: 0.93 (redução de 7% apenas, conforme pedido)
    calibrated_original = original_dist * 0.93
    calibrated_optimized = optimized_dist * 0.93

    optimized_nodes = []
    for idx in optimized_indices:
        n = nodes[idx - 1]
        optimized_nodes.append(n)

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

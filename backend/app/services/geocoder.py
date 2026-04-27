import aiohttp
import asyncio
import random
import logging
import re
from time import perf_counter
from typing import Dict, Optional, Tuple
from ..db.cache import cache_key_hash, get_cache_counters, get_cached_geocode, normalize_cache_key, reset_cache_counters, set_cached_geocode
from ..core.config import NOMINATIM_URL, USER_AGENT, RESTAURANTE_ENDERECO, RESTAURANTE_COORDS

logger = logging.getLogger("lucromaximo")

# Semáforo para respeitar o limite de 1 req/s do Nominatim (Política de Uso)
nominatim_sem = asyncio.Semaphore(1)
_geocoder_counters = {
    "provider_calls": 0,
    "provider_errors": 0,
}


def get_geocoder_counters() -> dict[str, int]:
    return {**get_cache_counters(), **_geocoder_counters}


def reset_geocoder_counters():
    for key in _geocoder_counters:
        _geocoder_counters[key] = 0
    reset_cache_counters()


def _log_geocode_event(event: str, key: str, query: str, status: str, elapsed_ms: float):
    logger.debug(
        "geocode_event event=%s key_hash=%s original_query_len=%d status=%s elapsed_ms=%.2f",
        event,
        cache_key_hash(key),
        len(query or ""),
        status,
        elapsed_ms,
    )

async def geocode_address(address: str) -> Optional[Dict]:
    """
    Geocodifica um endereço usando estratégias progressivas de forma assíncrona.
    """
    total_started = perf_counter()
    if not address: return None
    cache_key = normalize_cache_key(address)
    
    # 1. Atalho para o Restaurante (Instantâneo)
    if address.strip().lower() in [RESTAURANTE_ENDERECO.lower(), "recanto da feijoada", "origem"]:
        return {
            "lat": RESTAURANTE_COORDS[0], "lon": RESTAURANTE_COORDS[1],
            "display_name": RESTAURANTE_ENDERECO, "type": "restaurant", "weak": False
        }

    # 2. Verificar Cache (Instantâneo)
    cached, exists = get_cached_geocode(address)
    if exists:
        status = "hit" if cached else "miss"
        _log_geocode_event("geocode_total", cache_key, address, status, (perf_counter() - total_started) * 1000)
        return _apply_jitter(cached) if cached else None

    # 3. Preparação de Queries
    clean_addr = re.sub(r',?\s*Aracaju.*$', '', address, flags=re.IGNORECASE)
    clean_addr = re.sub(r'\b\d{5}[-,\.\s]?\d{3}\b', '', clean_addr)
    clean_addr = re.sub(r'\s+', ' ', clean_addr).strip().strip(",")
    
    cep_match = re.search(r'\b(\d{5}[-,\.\s]?\d{3})\b', address)
    cep = cep_match.group(1) if cep_match else None

    # Estratégias (Priorizamos Rua + Número)
    strategies = [
        {"name": "full", "query": f"{clean_addr}, Aracaju, SE, Brasil", "weak": False},
        {"name": "cep_num", "query": f"{re.search(r'(\d+)', address).group(1) if re.search(r'(\d+)', address) else ''}, {cep}, Aracaju, SE, Brasil", "weak": False} if cep else None,
        {"name": "cep_only", "query": f"{cep}, Aracaju, SE, Brasil", "weak": True} if cep else None
    ]
    strategies = [s for s in strategies if s is not None]

    # 4. Execução Controlada
    for s in strategies:
        async with nominatim_sem:
            provider_started = perf_counter()
            _geocoder_counters["provider_calls"] += 1
            try:
                result = await _fetch_nominatim(s['query'])
                status = "hit" if result else "miss"
            except Exception:
                _geocoder_counters["provider_errors"] += 1
                result = None
                status = "error"
                logger.exception(
                    "geocode_event event=provider_error key_hash=%s original_query_len=%d status=error elapsed_ms=%.2f",
                    cache_key_hash(cache_key),
                    len(address or ""),
                    (perf_counter() - provider_started) * 1000,
                )
            _log_geocode_event("provider_call", cache_key, address, status, (perf_counter() - provider_started) * 1000)
            # Delay obrigatório para não ser banido pelo Nominatim
            await asyncio.sleep(1.2)
        
        if result:
            res_data = {
                "lat": result[0],
                "lon": result[1],
                "display_name": result[2],
                "type": s['name'],
                "weak": s['weak']
            }
            # Cache e Jitter
            set_cached_geocode(address, res_data)
            _log_geocode_event("geocode_total", cache_key, address, "hit", (perf_counter() - total_started) * 1000)
            return _apply_jitter(res_data)

    set_cached_geocode(address, None)
    _log_geocode_event("geocode_total", cache_key, address, "miss", (perf_counter() - total_started) * 1000)
    return None

async def _fetch_nominatim(query: str) -> Optional[Tuple[float, float, str]]:
    """Chamada real à API via aiohttp."""
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "limit": 1
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(NOMINATIM_URL, params=params, timeout=10) as resp:
                if resp.status != 200: return None
                data = await resp.json()
                if not data: return None
                
                res = data[0]
                lat, lon = float(res["lat"]), float(res["lon"])
                display_name = res.get("display_name", "")
                
                # Validação de Aracaju (Rigidez Territorial)
                dist_centro = ((lat - (-10.9472))**2 + (lon - (-37.0731))**2)**0.5 * 111
                
                # Filtros de segurança
                is_outlier = any(x in display_name.lower() for x in ["itaporanga", "estancia", "lagarto"])
                
                if dist_centro < 25 and not is_outlier:
                    return (lat, lon, display_name)
                
                logger.warning("Nominatim Outlier descartado dist_km=%.1f", dist_centro)
                return None
    except Exception as e:
        logger.error(f"Erro aiohttp Nominatim: {e}")
        return None

def _apply_jitter(res: Dict) -> Dict:
    """Aplica o desvio de 10m para evitar colapso de endereços idênticos."""
    res = res.copy()
    res['lat'] += (random.random() - 0.5) * 0.0001
    res['lon'] += (random.random() - 0.5) * 0.0001
    return res

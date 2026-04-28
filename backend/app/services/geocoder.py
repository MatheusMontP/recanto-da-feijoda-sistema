import aiohttp
import asyncio
import random
import logging
import re
import unicodedata
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

NEIGHBORHOOD_FALLBACK_COORDS = {
    "13 de julho": (-10.9272, -37.0542),
    "america": (-10.9256, -37.0780),
    "atalaia": (-10.9850, -37.0500),
    "farolandia": (-10.9750, -37.0650),
    "grageru": (-10.9448, -37.0645),
    "inacio barbosa": (-10.9538, -37.0695),
    "jardins": (-10.9488, -37.0565),
    "ponto novo": (-10.9390, -37.0790),
    "santa maria": (-10.9800, -37.0990),
    "siqueira campos": (-10.9270, -37.0730),
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
        if not cached:
            fallback = _fallback_by_neighborhood(address)
            if fallback:
                set_cached_geocode(address, fallback)
                logger.warning(
                    "Cache negativo substituído por fallback de bairro address=%s lat=%.6f lon=%.6f display=%s",
                    address,
                    fallback["lat"],
                    fallback["lon"],
                    fallback["display_name"],
                )
                return _apply_jitter(fallback)
            _log_geocode_event("geocode_total", cache_key, address, "miss", (perf_counter() - total_started) * 1000)
            return None

        if (
            cached.get("weak")
            and cached.get("type") != "neighborhood_fallback"
            and not _weak_result_matches_cep(address, cached.get("display_name", ""))
        ):
            logger.warning(
                "Cache fraco descartado por CEP incompatível address=%s display=%s",
                address,
                cached.get("display_name", ""),
            )
        else:
            _log_geocode_event("geocode_total", cache_key, address, "hit", (perf_counter() - total_started) * 1000)
            return _apply_jitter(cached)

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
            if s["weak"] and not _weak_result_matches_cep(address, result[2]):
                logger.warning(
                    "Resultado fraco descartado por CEP incompatível address=%s display=%s",
                    address,
                    result[2],
                )
                continue

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

    fallback = _fallback_by_neighborhood(address)
    if fallback:
        set_cached_geocode(address, fallback)
        logger.warning(
            "Geocode fallback por bairro address=%s lat=%.6f lon=%.6f display=%s",
            address,
            fallback["lat"],
            fallback["lon"],
            fallback["display_name"],
        )
        return _apply_jitter(fallback)

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


def _extract_cep_digits(text: str) -> str | None:
    match = re.search(r"\b(\d{5})[-,\.\s]?(\d{3})\b", text or "")
    if not match:
        return None
    return f"{match.group(1)}{match.group(2)}"


def _weak_result_matches_cep(address: str, display_name: str) -> bool:
    expected_cep = _extract_cep_digits(address)
    if not expected_cep:
        return True
    returned_cep = _extract_cep_digits(display_name)
    return returned_cep == expected_cep


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _fallback_by_neighborhood(address: str) -> Optional[Dict]:
    normalized = _normalized_text(address)
    for neighborhood, coords in NEIGHBORHOOD_FALLBACK_COORDS.items():
        if neighborhood in normalized:
            return {
                "lat": coords[0],
                "lon": coords[1],
                "display_name": f"Fallback aproximado por bairro: {neighborhood}",
                "type": "neighborhood_fallback",
                "weak": True,
            }
    return None

def _apply_jitter(res: Dict) -> Dict:
    """Aplica o desvio de 10m para evitar colapso de endereços idênticos."""
    res = res.copy()
    res['lat'] += (random.random() - 0.5) * 0.0001
    res['lon'] += (random.random() - 0.5) * 0.0001
    return res

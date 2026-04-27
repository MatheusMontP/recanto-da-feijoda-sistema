import aiohttp
import asyncio
import random
import logging
import re
from typing import Dict, Optional, Tuple, List
from ..db.cache import get_cached_geocode, set_cached_geocode
from ..core.config import NOMINATIM_URL, USER_AGENT, URBAN_RADIUS_KM, RESTAURANTE_ENDERECO, RESTAURANTE_COORDS

logger = logging.getLogger("lucromaximo")

# Semáforo para respeitar o limite de 1 req/s do Nominatim (Política de Uso)
nominatim_sem = asyncio.Semaphore(1)

async def geocode_address(address: str) -> Optional[Dict]:
    """
    Geocodifica um endereço usando estratégias progressivas de forma assíncrona.
    """
    if not address: return None
    
    # 1. Atalho para o Restaurante (Instantâneo)
    if address.strip().lower() in [RESTAURANTE_ENDERECO.lower(), "recanto da feijoada", "origem"]:
        return {
            "lat": RESTAURANTE_COORDS[0], "lon": RESTAURANTE_COORDS[1],
            "display_name": RESTAURANTE_ENDERECO, "type": "restaurant", "weak": False
        }

    # 2. Verificar Cache (Instantâneo)
    cached, exists = get_cached_geocode(address)
    if exists and cached:
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
            result = await _fetch_nominatim(s['query'])
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
            final_res = _apply_jitter(res_data)
            set_cached_geocode(address, final_res)
            return final_res

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
                
                logger.warning(f"Nominatim Outlier: {display_name} ({dist_centro:.1f}km)")
                return None
    except Exception as e:
        logger.error(f"Erro aiohttp Nominatim: {e}")
        return None

def _apply_jitter(res: Dict) -> Dict:
    """Aplica o desvio de 10m para evitar colapso de endereços idênticos."""
    res['lat'] += (random.random() - 0.5) * 0.0001
    res['lon'] += (random.random() - 0.5) * 0.0001
    return res

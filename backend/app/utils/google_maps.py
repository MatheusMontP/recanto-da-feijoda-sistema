import asyncio
import logging
from typing import List, Optional

import requests

from ..services.geocoder import geocode_address

logger = logging.getLogger("lucromaximo")


async def _get_coords(address: str) -> Optional[str]:
    from ..core.config import RESTAURANTE_COORDS, RESTAURANTE_ENDERECO

    if address.strip().lower() in [RESTAURANTE_ENDERECO.lower(), "recanto da feijoada", "origem"]:
        return f"{RESTAURANTE_COORDS[1]},{RESTAURANTE_COORDS[0]}"

    res = await geocode_address(address)
    if res:
        return f"{res['lon']},{res['lat']}"
    return None


def _calculate_osrm_distance(coords: list[str]) -> Optional[float]:
    coords_str = ";".join(coords)
    logger.info("Calculando rota OSRM para %d pontos.", len(coords))
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=false"

    try:
        res = requests.get(url, timeout=10).json()
        if res.get("code") == "Ok":
            distance_m = res["routes"][0]["distance"]
            distance_km = (distance_m / 1000) * 1.03
            logger.info("Distância real calculada (OSRM + Calibração): %.2f km", distance_km)
            return distance_km
        logger.error("Erro na resposta do OSRM: %s - %s", res.get("code"), res.get("message"))
    except Exception as e:
        logger.error("Erro na API OSRM: %s", str(e))

    return None


def get_google_maps_distance(origin: str, stops: List[str], destination: Optional[str] = None) -> Optional[float]:
    return asyncio.run(get_google_maps_distance_async(origin, stops, destination))


async def get_google_maps_distance_async(origin: str, stops: List[str], destination: Optional[str] = None) -> Optional[float]:
    coords = []

    origin_coords = await _get_coords(origin)
    if not origin_coords:
        logger.error("Não foi possível geocodificar origem. original_query_len=%d", len(origin or ""))
        return None
    coords.append(origin_coords)

    for stop in stops:
        stop_coords = await _get_coords(stop)
        if stop_coords:
            coords.append(stop_coords)

    if destination:
        destination_coords = await _get_coords(destination)
        if destination_coords:
            coords.append(destination_coords)

    if len(coords) < 2:
        logger.warning("Coordenadas insuficientes para cálculo de distância: %d", len(coords))
        return None

    return await asyncio.to_thread(_calculate_osrm_distance, coords)

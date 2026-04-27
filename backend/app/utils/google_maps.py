import requests
import logging
from typing import List, Optional
from ..services.geocoder import geocode_address

logger = logging.getLogger("lucromaximo")

def get_google_maps_distance(origin: str, stops: List[str], destination: Optional[str] = None) -> Optional[float]:
    """
    Calculates the real driving distance using OSRM (Open Source Routing Machine).
    Uses the system's internal geocoder for accurate coordinate lookup.
    """
    from ..core.config import RESTAURANTE_ENDERECO, RESTAURANTE_COORDS

    def get_coords(address):
        # Atalho para o restaurante
        if address.strip().lower() in [RESTAURANTE_ENDERECO.lower(), "recanto da feijoada", "origem"]:
            return f"{RESTAURANTE_COORDS[1]},{RESTAURANTE_COORDS[0]}"
            
        res = geocode_address(address)
        if res:
            return f"{res['lon']},{res['lat']}"
        return None

    coords = []
    # Origin
    c = get_coords(origin)
    if not c: 
        logger.error(f"Não foi possível geocodificar origem: {origin}")
        return None
    coords.append(c)
    
    # Stops
    for stop in stops:
        c = get_coords(stop)
        if c: coords.append(c)
        
    # Destination
    if destination:
        c = get_coords(destination)
        if c: coords.append(c)
    
    if len(coords) < 2:
        logger.warning(f"Coordenadas insuficientes para cálculo de distância: {len(coords)}")
        return None

    # Call OSRM Route API
    coords_str = ";".join(coords)
    logger.info(f"Calculando rota OSRM para {len(coords)} pontos. Coords: {coords_str}")
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=false"
    
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("code") == "Ok":
            distance_m = res["routes"][0]["distance"]
            distance_km = (distance_m / 1000) * 1.03  # Ajuste para bater com Google Maps
            logger.info(f"Distância real calculada (OSRM + Calibração): {distance_km:.2f} km")
            return distance_km
        else:
            logger.error(f"Erro na resposta do OSRM: {res.get('code')} - {res.get('message')}")
    except Exception as e:
        logger.error(f"Erro na API OSRM: {str(e)}")
        
    return None

async def get_google_maps_distance_async(origin: str, stops: List[str], destination: Optional[str] = None) -> Optional[float]:
    import asyncio
    return await asyncio.to_thread(get_google_maps_distance, origin, stops, destination)

import time
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from ..db.cache import get_cached_geocode, set_cached_geocode
import re
from ..core.config import RESTAURANTE_ENDERECO, RESTAURANTE_COORDS
import logging

logger = logging.getLogger("lucromaximo")

# Revertendo para Nominatim com segurança reforçada
_geolocator = Nominatim(user_agent="lucromaximo_delivery_final_v5", timeout=15)
geocode_service = RateLimiter(_geolocator.geocode, min_delay_seconds=1.6, max_retries=3, error_wait_seconds=5.0)

def geocode_address(address: str):
    """
    Geocodifica um endereço com cache e estratégias otimizadas usando Nominatim.
    """
    if not address: return None
    
    # 1. Atalho para o Restaurante
    if address.strip().lower() in [RESTAURANTE_ENDERECO.lower(), "recanto da feijoada", "origem"]:
        return {
            "lat": RESTAURANTE_COORDS[0], "lon": RESTAURANTE_COORDS[1],
            "display_name": RESTAURANTE_ENDERECO, "type": "restaurant", "weak": False
        }

    # 2. Verificar Cache
    cached, exists = get_cached_geocode(address)
    if exists and cached:
        dist = ((cached['lat'] - (-10.94))**2 + (cached['lon'] - (-37.07))**2)**0.5 * 111
        if dist < 45:
            return cached

    # 3. Preparação
    original_address = address
    cep_match = re.search(r'\b(\d{5}[-,\.\s]?\d{3})\b', address)
    cep = cep_match.group(1) if cep_match else None
    
    # Limpeza para Nominatim
    clean_addr = re.sub(r',?\s*Aracaju.*$', '', address, flags=re.IGNORECASE)
    clean_addr = re.sub(r'\b\d{5}[-,\.\s]?\d{3}\b', '', clean_addr)
    clean_addr = re.sub(r'\s+', ' ', clean_addr).strip().strip(",")

    # Extrair Bairro se possível
    bairro_found = None
    bairros_conhecidos = ["atalaia", "aruana", "santa maria", "aeroporto", "farolandia", "coroa do meio", "jardins", "grageru"]
    for b in bairros_conhecidos:
        if b in address.lower():
            bairro_found = b
            break

    strategies = [
        # Estratégia 1: Endereço completo (Rua, Número, Bairro) - A mais assertiva
        {"name": "full_specific", "query": f"{clean_addr}, Aracaju, SE, Brasil", "weak": False},
        
        # Estratégia 2: CEP + Número (Fallback caso a rua tenha nome comum)
        {"name": "cep_num", "query": f"{re.search(r'(\d+)', address).group(1) if re.search(r'(\d+)', address) else ''}, {cep}, Aracaju, SE, Brasil", "weak": False} if cep else None,
        
        # Estratégia 3: Bairro puro (Para pontos imprecisos)
        {"name": "bairro_only", "query": f"{bairro_found}, Aracaju, SE, Brasil", "weak": True} if bairro_found else None,
        
        # Estratégia 4: CEP Puro (Último recurso)
        {"name": "cep_only", "query": f"{cep}, Aracaju, SE, Brasil", "weak": True} if cep else None
    ]
    strategies = [s for s in strategies if s is not None]

    # Execução
    local_cities = ["aracaju", "sao cristovao", "barra dos coqueiros", "nossa senhora do socorro", "socorro", "atalaia", "farolandia"]
    
    for s in strategies:
        try:
            logger.info(f"Nominatim Geocodificando ({s['name']}): {s['query']}")
            location = geocode_service(s['query'])
            
            if location:
                addr_lower = location.address.lower()
                # Verifica se o resultado pertence à Grande Aracaju
                is_local = any(city in addr_lower for city in local_cities)
                
                if not is_local:
                    logger.warning(f"Nominatim: Ignorando resultado fora da região local: {location.address}")
                    continue

                res = {
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "display_name": location.address,
                    "type": s['name'],
                    "weak": s['weak']
                }
                
                # Validação específica para o bairro Santa Maria (deve ser Zona Sul)
                if bairro_found == "santa maria" and res['lat'] > -10.96:
                     logger.warning(f"Nominatim: Santa Maria detectado na Zona Norte? Ignorando. {location.address}")
                     continue

                # Validação geográfica (raio de 25km para cobrir do Mosqueiro até o Porto d'Antas)
                dist = ((res['lat'] - (-10.9472))**2 + (res['lon'] - (-37.0731))**2)**0.5 * 111
                
                # Filtro de texto: Só aceita se for Aracaju ou região metropolitana IMEDIATA
                display_name = location.address.lower()
                is_aracaju = "aracaju" in display_name or "aruana" in display_name or "mosqueiro" in display_name
                is_outlier = "itaporanga" in display_name or "estância" in display_name or "lagarto" in display_name
                
                if dist < 25 and is_aracaju and not is_outlier:
                    # Jitter: Se a coordenada for idêntica a algo que já processamos, damos um totó
                    # (Lógica simples: usamos o timestamp para dar um offset de ~5-10 metros)
                    import random
                    res['lat'] += (random.random() - 0.5) * 0.0001
                    res['lon'] += (random.random() - 0.5) * 0.0001
                    
                    set_cached_geocode(original_address, res)
                    return res
                else:
                    logger.warning(f"Nominatim: Localização descartada (Longe/Fora de Aracaju): {location.address} ({dist:.1f}km)")
                    return {"error": "imprecise", "dist": dist, "address": location.address}
        except Exception as e:
            logger.error(f"Erro Nominatim: {str(e)}")
            time.sleep(2)

    return None

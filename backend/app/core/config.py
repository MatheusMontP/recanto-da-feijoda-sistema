import os

RESTAURANTE_NOME = "Recanto da Feijoada"
RESTAURANTE_ENDERECO = "R. Brasílio Martinho Vale, 46 - Farolândia, Aracaju - SE"
RESTAURANTE_COORDS = (-10.97075, -37.06333)

MAX_PARADAS_POR_BLOCO = 12
CACHE_DB = "geocache_v7.db"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RecantoFeijoada_Logistics_v10"
URBAN_RADIUS_KM = 35.0  # Expandido para cobrir do Mosqueiro até o Porto d'Antas
ARACAJU_BOUNDS = [-37.25, -11.15, -36.90, -10.80] # [minLon, minLat, maxLon, maxLat]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

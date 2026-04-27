import os

RESTAURANTE_NOME = "Recanto da Feijoada"
RESTAURANTE_ENDERECO = "R. Brasílio Martinho Vale, 46 - Farolândia, Aracaju - SE"
RESTAURANTE_COORDS = (-10.97075, -37.06333)

MAX_PARADAS_POR_BLOCO = 15
CACHE_DB = "geocache_v6.db"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

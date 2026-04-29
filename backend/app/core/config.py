import os


def _parse_csv_env(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    values = [item.strip() for item in raw.split(",")]
    return [item for item in values if item]

RESTAURANTE_ENDERECO = "R. Brasílio Martinho Vale, 46 - Farolândia, Aracaju - SE"
RESTAURANTE_COORDS = (-10.97075, -37.06333)

MAX_PARADAS_POR_BLOCO = 12
CACHE_DB = "geocache_v7.db"

APP_ENV = os.getenv("APP_ENV", "development").lower()
CORS_ORIGINS = _parse_csv_env(
    "CORS_ORIGINS",
    ["http://127.0.0.1:8000", "http://localhost:8000"] if APP_ENV == "production" else ["*"],
)
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RecantoFeijoada_Logistics_v10"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

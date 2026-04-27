import sqlite3
import json
import logging
from ..core.config import CACHE_DB

logger = logging.getLogger("lucromaximo")

_geocode_cache: dict[str, dict | None] = {}

def init_db():
    try:
        conn = sqlite3.connect(CACHE_DB)
        conn.execute("CREATE TABLE IF NOT EXISTS geocache (query TEXT PRIMARY KEY, data TEXT)")
        conn.close()
        logger.info("Banco de dados de cache pronto.")
    except Exception as e:
        logger.warning("Erro ao inicializar DB de cache: %s", e)

def get_cached_geocode(query: str) -> tuple[dict | None, bool]:
    if query in _geocode_cache:
        data = _geocode_cache[query]
        if data and _is_local(data.get("display_name", "")):
            return data, True
        
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.execute("SELECT data FROM geocache WHERE query = ?", (query,))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            # Validação extra para limpar lixo histórico do cache
            if data and not _is_local(data.get("display_name", "")):
                logger.warning(f"Cache descartado por localidade inválida: {data.get('display_name')}")
                return None, False
                
            _geocode_cache[query] = data
            return data, True
    except Exception as e:
        logger.warning("Erro ao ler cache: %s", e)
    return None, False

def _is_local(display_name: str) -> bool:
    """Verifica se o nome do local pertence à região de Aracaju."""
    if not display_name: return False
    dn = display_name.lower()
    local_cities = ["aracaju", "sao cristovao", "barra dos coqueiros", "socorro", "sergipe", " se,"]
    return any(city in dn for city in local_cities)

def set_cached_geocode(query: str, data: dict | None):
    _geocode_cache[query] = data
    if data is None:
        return
        
    try:
        conn = sqlite3.connect(CACHE_DB)
        conn.execute("CREATE TABLE IF NOT EXISTS geocache (query TEXT PRIMARY KEY, data TEXT)")
        conn.execute("INSERT OR REPLACE INTO geocache (query, data) VALUES (?, ?)", 
                     (query, json.dumps(data)))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Erro ao salvar cache: %s", e)

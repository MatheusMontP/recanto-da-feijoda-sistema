import json
import logging
import re
import sqlite3
import unicodedata
import hashlib
from contextlib import closing
from datetime import datetime, timedelta, timezone
from time import perf_counter

from ..core.config import CACHE_DB

logger = logging.getLogger("lucromaximo")

POSITIVE_TTL_DAYS = 120
NEGATIVE_TTL_HOURS = 12

_geocode_cache: dict[str, tuple[dict | None, str, str | None]] = {}
_cache_counters = {
    "hits": 0,
    "misses": 0,
    "negative_hits": 0,
    "expired": 0,
}


def normalize_cache_key(query: str) -> str:
    value = unicodedata.normalize("NFKD", query or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\s*(?:,|/|-)?\s*aracaju\s*(?:(?:,|/|-)\s*se)?\s*(?:(?:,|/|-)\s*brasil)?\s*$", "", value)
    value = re.sub(r"\s*(?:,|/|-)?\s*se\s*(?:(?:,|/|-)\s*brasil)?\s*$", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,")
    return value


def cache_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def get_cache_counters() -> dict[str, int]:
    return dict(_cache_counters)


def reset_cache_counters():
    for key in _cache_counters:
        _cache_counters[key] = 0


def _log_cache_event(event: str, key: str, query: str, status: str, elapsed_ms: float):
    logger.debug(
        "geocode_cache_event event=%s key_hash=%s original_query_len=%d status=%s elapsed_ms=%.2f",
        event,
        cache_key_hash(key),
        len(query or ""),
        status,
        elapsed_ms,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) <= _now()
    except ValueError:
        return True


def _ensure_schema(conn: sqlite3.Connection):
    conn.execute("CREATE TABLE IF NOT EXISTS geocache (query TEXT PRIMARY KEY, data TEXT)")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(geocache)")}
    columns = {
        "original_query": "TEXT",
        "status": "TEXT DEFAULT 'hit'",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "expires_at": "TEXT",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE geocache ADD COLUMN {name} {definition}")


def init_db():
    try:
        with closing(sqlite3.connect(CACHE_DB)) as conn:
            _ensure_schema(conn)
            conn.commit()
        logger.info("Banco de dados de cache pronto.")
    except Exception as e:
        logger.warning("Erro ao inicializar DB de cache: %s", e)


def get_cached_geocode(query: str) -> tuple[dict | None, bool]:
    started = perf_counter()
    key = normalize_cache_key(query)
    if key in _geocode_cache:
        data, status, expires_at = _geocode_cache[key]
        if not _is_expired(expires_at):
            if status == "miss":
                _cache_counters["negative_hits"] += 1
                _log_cache_event("cache_negative_hit", key, query, "miss", (perf_counter() - started) * 1000)
            else:
                _cache_counters["hits"] += 1
                _log_cache_event("cache_hit", key, query, "hit", (perf_counter() - started) * 1000)
            return data, True
        _geocode_cache.pop(key, None)
        _cache_counters["expired"] += 1
        _log_cache_event("cache_expired", key, query, "expired", (perf_counter() - started) * 1000)

    try:
        with closing(sqlite3.connect(CACHE_DB)) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT data, status, expires_at FROM geocache WHERE query = ?",
                (key,),
            ).fetchone()
        if not row:
            _cache_counters["misses"] += 1
            _log_cache_event("cache_miss", key, query, "miss", (perf_counter() - started) * 1000)
            return None, False

        data_raw, status, expires_at = row
        if _is_expired(expires_at):
            _cache_counters["expired"] += 1
            _log_cache_event("cache_expired", key, query, "expired", (perf_counter() - started) * 1000)
            return None, False

        data = json.loads(data_raw) if data_raw else None
        if status == "miss":
            _geocode_cache[key] = (None, "miss", expires_at)
            _cache_counters["negative_hits"] += 1
            _log_cache_event("cache_negative_hit", key, query, "miss", (perf_counter() - started) * 1000)
            return None, True

        if data and not _is_local(data.get("display_name", "")):
            logger.warning("Cache descartado por localidade invalida key_hash=%s", cache_key_hash(key))
            _cache_counters["misses"] += 1
            _log_cache_event("cache_miss", key, query, "miss", (perf_counter() - started) * 1000)
            return None, False

        _geocode_cache[key] = (data, "hit", expires_at)
        _cache_counters["hits"] += 1
        _log_cache_event("cache_hit", key, query, "hit", (perf_counter() - started) * 1000)
        return data, True
    except Exception as e:
        logger.warning("Erro ao ler cache: %s", e)
    _cache_counters["misses"] += 1
    _log_cache_event("cache_miss", key, query, "error", (perf_counter() - started) * 1000)
    return None, False


def _is_local(display_name: str) -> bool:
    if not display_name:
        return False
    dn = display_name.lower()
    local_cities = ["aracaju", "sao cristovao", "barra dos coqueiros", "socorro", "sergipe", " se,"]
    return any(city in dn for city in local_cities)


def set_cached_geocode(query: str, data: dict | None):
    key = normalize_cache_key(query)
    now = _now()
    status = "hit" if data is not None else "miss"
    expires_at = _iso(now + (timedelta(days=POSITIVE_TTL_DAYS) if data else timedelta(hours=NEGATIVE_TTL_HOURS)))

    try:
        with closing(sqlite3.connect(CACHE_DB)) as conn:
            _ensure_schema(conn)
            if data is None:
                row = conn.execute(
                    "SELECT status, expires_at FROM geocache WHERE query = ?",
                    (key,),
                ).fetchone()
                if row and row[0] != "miss" and not _is_expired(row[1]):
                    return

            conn.execute(
                """
                INSERT INTO geocache (query, original_query, data, status, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(query) DO UPDATE SET
                    original_query = excluded.original_query,
                    data = excluded.data,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (key, query, json.dumps(data) if data else None, status, _iso(now), _iso(now), expires_at),
            )
            conn.commit()
        _geocode_cache[key] = (data, status, expires_at)
    except Exception as e:
        logger.warning("Erro ao salvar cache: %s", e)

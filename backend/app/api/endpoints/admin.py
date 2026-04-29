import logging

from fastapi import APIRouter, Header, HTTPException, status

from ...core.config import ADMIN_TOKEN
from ...db.cache import clear_geocode_cache

router = APIRouter()
logger = logging.getLogger("lucromaximo")


def _verify_admin_token(x_admin_token: str | None):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ADMIN_TOKEN_NOT_CONFIGURED",
                "message": "Configure ADMIN_TOKEN antes de usar endpoints administrativos.",
            },
        )
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Token administrativo invalido."},
        )


@router.post("/admin/cache/clear")
def clear_cache_endpoint(x_admin_token: str | None = Header(default=None)):
    _verify_admin_token(x_admin_token)
    result = clear_geocode_cache()
    logger.warning(
        "admin_cache_clear deleted_rows=%d memory_entries=%d",
        result["deleted_rows"],
        result["memory_entries"],
    )
    return {"status": "ok", **result}

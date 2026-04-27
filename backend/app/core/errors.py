import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

logger = logging.getLogger("lucromaximo")


def error_payload(code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        }
    }


async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    code = "HTTP_ERROR"
    message = "Não foi possível concluir a operação."
    details = []

    if isinstance(detail, dict):
        code = detail.get("code", code)
        message = detail.get("message", message)
        details = detail.get("details", [])
        if "retry_after" in detail:
            details = [*details, {"retry_after": detail["retry_after"]}]
    elif isinstance(detail, str):
        message = detail

    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, message, details),
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "VALIDATION_ERROR",
            "Revise os dados enviados e tente novamente.",
            jsonable_encoder(exc.errors()),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Erro não tratado em %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            "INTERNAL_SERVER_ERROR",
            "Erro interno ao processar a solicitação.",
        ),
    )

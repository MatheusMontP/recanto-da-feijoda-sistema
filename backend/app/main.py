import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .api.endpoints import admin, delivery
from .core.config import CORS_ORIGINS, FRONTEND_DIR
from .core.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from .db.cache import init_db

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lucromaximo")

# Initialize Cache DB
init_db()

app = FastAPI(
    title="LucroMáximo Logistics",
    description="API de roteirização de entregas com otimização geográfica (Modular Architecture).",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Include Routers
app.include_router(delivery.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/app/")

# Serve Frontend
if os.path.exists(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.warning("Frontend directory not found at %s", FRONTEND_DIR)

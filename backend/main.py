"""
LucroMáximo Logistics — Entrypoint
Este arquivo atua como um wrapper para a nova arquitetura modular.
"""
try:
    # Render/start command from repo root: uvicorn backend.main:app
    from .app.main import app
except ImportError:
    # Local start from backend/: uvicorn main:app
    from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

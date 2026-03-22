"""
app/main.py

Ponto de entrada da aplicação FastAPI.
Application factory com registro de routers, middlewares e lifespan.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import create_all_tables
import app.models_registry  # noqa: F401 — garante registro de todos os modelos

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown da aplicação."""
    logger.info(f"Iniciando {settings.APP_NAME} v{settings.APP_VERSION}...")

    # Cria diretórios necessários
    Path(settings.REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    Path("./static/img").mkdir(parents=True, exist_ok=True)

    # Em desenvolvimento: criar tabelas automaticamente
    if settings.APP_ENV == "development":
        try:
            await create_all_tables()
            logger.info("Tabelas verificadas/criadas (modo desenvolvimento).")
        except Exception as e:
            logger.warning(f"Não foi possível criar tabelas automaticamente: {e}")

    logger.info(f"{settings.APP_NAME} iniciado com sucesso.")
    yield
    logger.info(f"{settings.APP_NAME} encerrado.")


def create_app() -> FastAPI:
    """Factory da aplicação FastAPI."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Sistema profissional de estudos elétricos de proteção, "
            "dimensionamento e coordenação de sistemas de potência. "
            "Produzido por BK Engenharia e Tecnologia."
        ),
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ─── Middlewares ───────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Arquivos estáticos ────────────────────────────────────────────────────
    static_path = Path(settings.STATIC_DIR)
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # ─── Templates ────────────────────────────────────────────────────────────
    templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)

    # ─── Routers ──────────────────────────────────────────────────────────────
    from app.auth.router import router as auth_router
    from app.calculations.router import router as calc_router
    from app.projects.router import router as projects_router
    from app.studies.router import router as studies_router, api_router as studies_api_router
    from app.reports.router import router as reports_router
    from app.cables.router import router as cables_router

    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(studies_router)
    app.include_router(studies_api_router)
    app.include_router(calc_router)
    app.include_router(reports_router)
    app.include_router(cables_router)

    # ─── Rotas de páginas HTML ────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Redireciona para dashboard ou login."""
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            "dashboard/index.html",
            {
                "request": request,
                "title": "Dashboard",
                "app_name": settings.APP_NAME,
                "app_version": settings.APP_VERSION,
            },
        )

    # ─── Handlers de erro ────────────────────────────────────────────────────
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Recurso não encontrado."}, status_code=404)
        return templates.TemplateResponse(
            "partials/_error.html",
            {"request": request, "error": "Página não encontrada.", "code": 404},
            status_code=404,
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):
        logger.exception(f"Erro interno: {exc}")
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Erro interno do servidor."}, status_code=500)
        return templates.TemplateResponse(
            "partials/_error.html",
            {"request": request, "error": "Erro interno do servidor.", "code": 500},
            status_code=500,
        )

    return app


# Instância da aplicação (para Uvicorn / Railway)
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
    )

"""Aplicação FastAPI — Saúde RJ.

Placeholder bootstrap (Fase 0). Os routers reais são adicionados nas próximas fases.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.routers import audio as audio_router
from app.routers import auth as auth_router
from app.routers import dashboards as dashboards_router
from app.routers import equipes as equipes_router
from app.routers import gestao as gestao_router
from app.routers import ia as ia_router
from app.routers import pacientes as pacientes_router
from app.routers import planner as planner_router
from app.routers import registros as registros_router
from app.routers import relatorios as relatorios_router

configure_logging()

app = FastAPI(
    title="Saúde RJ — API",
    description="Planner e roteirizador para ACS do Rio de Janeiro.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Endpoint de saúde — usado para verificar se a API está no ar."""
    return {"status": "ok", "service": "saude-rj-api"}


app.include_router(auth_router.router)
app.include_router(pacientes_router.router)
app.include_router(equipes_router.router)
app.include_router(planner_router.router)
app.include_router(registros_router.router)
app.include_router(dashboards_router.router)
app.include_router(relatorios_router.router)
app.include_router(ia_router.router)
app.include_router(audio_router.router)
app.include_router(gestao_router.router)

"""Schemas do planner — DTOs de rota e itens visitáveis."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from app.db.models import NivelRisco


class ItemRota(BaseModel):
    """Um paciente dentro da rota do dia."""

    ordem: int
    paciente_id: int
    nome_display: str
    score_combinado: float
    nivel_risco: NivelRisco | None
    score_risco: float | None
    distancia_km: float
    dias_sem_visita: int | None
    componentes: dict[str, Any]
    motivos: list[str]
    latitude: float
    longitude: float
    status: str = "pendente"


class RotaDia(BaseModel):
    profissional_id: int
    profissional_nome: str | None
    equipe_id: int | None
    data: date
    itens: list[ItemRota]
    distancia_total_km: float
    pesos: dict[str, float]
    gerado_em: str


class RotaSemana(BaseModel):
    profissional_id: int
    dias: list[RotaDia]


class RotaPeriodo(BaseModel):
    profissional_id: int
    inicio: date
    fim: date
    dias: list[RotaDia]


class RecalcularRequest(BaseModel):
    profissional_id: int | None = None
    inicio: date
    fim: date
    pesos: dict[str, float] | None = None  # override w_risco/w_proximidade/w_recencia
    n_max_visitas_dia: int | None = None

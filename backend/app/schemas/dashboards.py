"""Schemas dos dashboards e relatórios."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.db.models import NivelRisco


class KpisDashboard(BaseModel):
    """KPIs principais do escopo do usuário."""

    pacientes_total: int
    pacientes_criticos: int
    pacientes_alto_risco: int
    pacientes_vulneraveis: int
    gestantes: int
    hipertensos: int
    diabeticos: int
    idosos: int
    criancas_0_6: int
    sem_visita_90d: int
    sem_visita_180d: int
    visitas_ultimo_mes: int
    eventos_urgencia_30d: int
    score_medio: float
    escopo: str  # "Admin (todos)" | "AP-01" | "Unidade Xxxx" | "Equipe Yyyy"


PontoMapa = tuple[float, float]


class PontoPaciente(BaseModel):
    paciente_id: int
    lat: float
    lon: float
    nivel_risco: NivelRisco | None
    nome_display: str


class MapaResponse(BaseModel):
    """Pontos individuais (limitados) + sede da equipe / unidade."""

    pacientes: list[PontoPaciente]
    sedes_equipes: list[dict]  # {"equipe_id", "nome", "lat", "lon"}
    sedes_unidades: list[dict]
    total_no_escopo: int
    truncado_em: int | None


HeatmapTipo = Literal["vulnerabilidade", "urgencia", "sem_visita"]


class HeatmapResponse(BaseModel):
    tipo: HeatmapTipo
    pontos: list[tuple[float, float, float]]  # (lat, lon, intensidade)
    total: int


class ItemRanking(BaseModel):
    paciente_id: int
    nome_display: str
    score: float
    nivel_risco: NivelRisco | None
    ultima_visita_em: date | None
    motivos: list[str]


class RankingPacientes(BaseModel):
    items: list[ItemRanking]
    escopo: str


# ---------------------------------------------------------------------------
# Relatórios
# ---------------------------------------------------------------------------


class RelatorioACSDia(BaseModel):
    """Dados do relatório one-page imprimível do ACS para um dia."""

    profissional_id: int
    profissional_nome: str
    equipe_id: int | None
    data: date
    gerado_em: str
    rota: dict  # estrutura do RotaDia
    pacientes_criticos_alertas: list[dict]  # subset com alertas críticos
    totais: dict


class RelatorioGestor(BaseModel):
    """Relatório consolidado para gestor (unidade ou AP)."""

    escopo: str
    inicio: date
    fim: date
    gerado_em: str
    totais: dict
    riscos_por_equipe: list[dict]
    pacientes_criticos: list[dict]
    alertas_principais: list[dict]

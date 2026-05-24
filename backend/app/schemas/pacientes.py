"""Schemas dos pacientes — DTOs leves para listagem e detalhe."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.db.models import NivelRisco, TipoEventoClinico


class PacienteResumo(BaseModel):
    """Resumo usado em listagens (planner, mapa, ranking)."""

    id: int
    hash_id: str
    nome_display: str
    faixa_etaria: str
    sexo: str
    situacao_vulnerabilidade: bool
    hipertenso: bool
    diabetico: bool
    gestacao: bool
    endereco_latitude: float
    endereco_longitude: float
    coordenada_outlier: bool
    score_atual: float | None
    nivel_risco: NivelRisco | None
    ultima_visita_em: date | None
    equipe_id: int | None
    unidade_id: int | None
    ap_id: int | None
    bairro_id: int | None


class PacienteDetalhe(PacienteResumo):
    raca_cor: str | None
    fatores_risco: list[dict[str, Any]] = []
    ficha_sugerida: str | None = None


class TimelineItem(BaseModel):
    """Item da linha do tempo do paciente — visita, evento, registro etc."""

    tipo: str  # "visita" | "evento_clinico" | "registro_visita"
    data: date
    rotulo: str
    detalhes: dict[str, Any] = {}


class TimelinePaciente(BaseModel):
    paciente_id: int
    itens: list[TimelineItem]


class EventoClinicoOut(BaseModel):
    id: int
    paciente_id: int
    tipo: TipoEventoClinico
    data_referencia: date


class VisitaOut(BaseModel):
    id: int
    paciente_id: int
    profissional_id: int
    data: date
    ordem_visita_dia: int | None


class ListResponse(BaseModel):
    """Resposta paginada genérica."""

    total: int
    items: list[Any]

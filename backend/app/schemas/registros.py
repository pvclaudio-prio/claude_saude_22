"""Schemas de RegistroVisita — request/response da API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import FichaTipo, OrigemRegistro, StatusVisita


class ViolenciaInfo(BaseModel):
    suspeita: bool = False
    tipo: str | None = None
    descricao: str | None = None
    encaminhamentos: list[str] = Field(default_factory=list)


class RegistroVisitaIn(BaseModel):
    paciente_id: int
    ficha_tipo: FichaTipo = FichaTipo.LIVRE
    respostas: dict[str, Any] = Field(default_factory=dict)

    resumo: str | None = None
    sinais_risco: list[str] = Field(default_factory=list)
    violencia: ViolenciaInfo | None = None
    necessidades_especiais: list[str] = Field(default_factory=list)
    encaminhamentos: list[str] = Field(default_factory=list)
    proxima_acao: str | None = None
    prazo_retorno: date | None = None

    status: StatusVisita = StatusVisita.VISITADO

    # Marcadores quando o registro veio do fluxo de áudio + IA
    origem: OrigemRegistro = OrigemRegistro.MANUAL
    confianca_ia: float | None = Field(default=None, ge=0.0, le=1.0)
    campos_baixa_confianca: list[str] = Field(default_factory=list)


class RegistroVisitaPatch(BaseModel):
    """Edição parcial — todos os campos opcionais."""

    ficha_tipo: FichaTipo | None = None
    respostas: dict[str, Any] | None = None
    resumo: str | None = None
    sinais_risco: list[str] | None = None
    violencia: ViolenciaInfo | None = None
    necessidades_especiais: list[str] | None = None
    encaminhamentos: list[str] | None = None
    proxima_acao: str | None = None
    prazo_retorno: date | None = None
    status: StatusVisita | None = None


class RegistroVisitaOut(BaseModel):
    id: int
    paciente_id: int
    profissional_id: int
    criado_em: datetime
    criado_por_user_id: int | None
    origem: OrigemRegistro

    ficha_tipo: FichaTipo
    respostas: dict[str, Any]

    resumo: str | None
    sinais_risco: list[str]
    violencia: dict[str, Any] | None
    necessidades_especiais: list[str]
    encaminhamentos: list[str]
    proxima_acao: str | None
    prazo_retorno: date | None

    status: StatusVisita
    confianca_ia: float | None
    campos_baixa_confianca: list[str]

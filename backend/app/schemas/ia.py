"""Schemas dos endpoints de IA."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurno(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Payload do chat — histórico em formato simplificado (texto)."""

    mensagens: list[ChatTurno] = Field(default_factory=list)
    pergunta: str


class SintesePacienteRequest(BaseModel):
    paciente_id: int


class BriefingRotaRequest(BaseModel):
    data: str | None = None  # YYYY-MM-DD


class SinteseResponse(BaseModel):
    sintese: str
    contexto_usado: dict[str, Any]


class BriefingResponse(BaseModel):
    briefing: str
    rota_resumo: dict[str, Any]

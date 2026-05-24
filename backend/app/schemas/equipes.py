"""Schemas de equipes, unidades, AP, bairros, profissionais."""

from __future__ import annotations

from pydantic import BaseModel

from app.db.models import UserRole


class AreaProgramaticaOut(BaseModel):
    id: int
    nome: str
    derivado: bool
    centro_lat: float | None
    centro_lon: float | None


class BairroOut(BaseModel):
    id: int
    nome: str
    ap_id: int | None
    derivado: bool


class UnidadeOut(BaseModel):
    id: int
    hash_id: str
    nome_display: str
    ap_id: int | None
    bairro_id: int | None
    centro_lat: float | None
    centro_lon: float | None


class EquipeOut(BaseModel):
    id: int
    hash_id: str
    nome_display: str
    unidade_id: int | None
    ap_id: int | None
    bairro_id: int | None
    sede_lat: float
    sede_lon: float


class ProfissionalOut(BaseModel):
    id: int
    hash_id: str
    nome_display: str
    role: UserRole
    equipe_id: int | None
    unidade_id: int | None
    ap_id: int | None
    ativo: bool

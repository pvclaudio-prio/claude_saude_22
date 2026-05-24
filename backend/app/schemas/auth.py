"""Schemas de autenticação demo."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.models import UserRole


class LoginDemoRequest(BaseModel):
    username: str


class LoginDemoResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    username: str
    nome_display: str
    role: UserRole
    profissional_id: int | None = None
    equipe_id: int | None = None
    unidade_id: int | None = None
    ap_id: int | None = None


LoginDemoResponse.model_rebuild()

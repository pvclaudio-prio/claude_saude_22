"""Auth demo + RBAC.

Decisões registradas:
- Token bag **em memória** (`dict[token, user_id]`) é suficiente para o piloto
  e simplifica o login demo. Em produção real: JWT assinado / sessão Redis.
- `require_roles(...)` é uma factory de dependência para proteger endpoints.
- `apply_scope_filter(query, user, model)` aplica o filtro de escopo ao
  query conforme o papel — defesa em profundidade no backend.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.sql import Select
from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import User, UserRole
from app.db.session import get_session

log = get_logger("security")

# token -> (user_id, expira_em)
_TOKEN_BAG: dict[str, tuple[int, datetime]] = {}


# ---------------------------------------------------------------------------
# Token bag
# ---------------------------------------------------------------------------


def issue_token(user_id: int) -> tuple[str, datetime]:
    """Gera token opaco e armazena na bag em memória."""
    token = secrets.token_urlsafe(32)
    expira = datetime.now(UTC) + timedelta(minutes=settings.auth_token_ttl_min)
    _TOKEN_BAG[token] = (user_id, expira)
    return token, expira


def revoke_token(token: str) -> None:
    _TOKEN_BAG.pop(token, None)


def resolve_token(token: str) -> int | None:
    """Devolve o user_id do token se válido e não expirado; senão None."""
    entry = _TOKEN_BAG.get(token)
    if entry is None:
        return None
    user_id, expira = entry
    if datetime.now(UTC) > expira:
        _TOKEN_BAG.pop(token, None)
        return None
    return user_id


# ---------------------------------------------------------------------------
# Dependências
# ---------------------------------------------------------------------------


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Lê `Authorization: Bearer <token>`, resolve o usuário."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Formato inválido")
    user_id = resolve_token(parts[1])
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")
    user = session.get(User, user_id)
    if user is None or not user.ativo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inativo")
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Factory: dependência que exige um dos papéis informados."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            log.warning("rbac.denied", user=user.username, role=user.role.value, esperado=[r.value for r in roles])
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão insuficiente")
        return user

    return _dep


# ---------------------------------------------------------------------------
# Escopo (defesa em profundidade)
# ---------------------------------------------------------------------------


def apply_paciente_scope(query: Select[Any], user: User) -> Select[Any]:
    """Filtra um Select[Paciente] conforme o escopo do usuário."""
    from app.db.models import Paciente, Profissional, Visita

    if user.role is UserRole.ADMIN:
        return query
    if user.role is UserRole.GESTOR_AP and user.ap_id is not None:
        return query.where(Paciente.ap_id == user.ap_id)
    if user.role is UserRole.GESTOR_UNIDADE and user.unidade_id is not None:
        return query.where(Paciente.unidade_id == user.unidade_id)
    if user.role is UserRole.ACS:
        # ACS vê (a) pacientes da sua equipe + (b) pacientes que ele já visitou
        # (defensivo: profissional pode estar atribuído fora da equipe modal).
        if user.equipe_id is None and user.profissional_id is None:
            # sem vínculo → nada
            return query.where(False)
        conditions = []
        if user.equipe_id is not None:
            conditions.append(Paciente.equipe_id == user.equipe_id)
        if user.profissional_id is not None:
            sub = select(Visita.paciente_id).where(Visita.profissional_id == user.profissional_id)
            conditions.append(Paciente.id.in_(sub))  # type: ignore[attr-defined]
        from sqlalchemy import or_

        return query.where(or_(*conditions))
    # Default seguro: nega tudo
    return query.where(False)


def apply_equipe_scope(query: Select[Any], user: User) -> Select[Any]:
    from app.db.models import Equipe

    if user.role is UserRole.ADMIN:
        return query
    if user.role is UserRole.GESTOR_AP and user.ap_id is not None:
        return query.where(Equipe.ap_id == user.ap_id)
    if user.role is UserRole.GESTOR_UNIDADE and user.unidade_id is not None:
        return query.where(Equipe.unidade_id == user.unidade_id)
    if user.role is UserRole.ACS and user.equipe_id is not None:
        return query.where(Equipe.id == user.equipe_id)
    return query.where(False)


def apply_profissional_scope(query: Select[Any], user: User) -> Select[Any]:
    from app.db.models import Profissional

    if user.role is UserRole.ADMIN:
        return query
    if user.role is UserRole.GESTOR_AP and user.ap_id is not None:
        return query.where(Profissional.ap_id == user.ap_id)
    if user.role is UserRole.GESTOR_UNIDADE and user.unidade_id is not None:
        return query.where(Profissional.unidade_id == user.unidade_id)
    if user.role is UserRole.ACS:
        if user.profissional_id is None:
            return query.where(False)
        return query.where(Profissional.id == user.profissional_id)
    return query.where(False)

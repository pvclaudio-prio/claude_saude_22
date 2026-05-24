"""Endpoints de autenticação demo."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.core.security import get_current_user, issue_token, revoke_token
from app.db.models import User
from app.db.session import get_session
from app.schemas.auth import LoginDemoRequest, LoginDemoResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("routers.auth")


@router.post("/login-demo", response_model=LoginDemoResponse)
def login_demo(payload: LoginDemoRequest, session: Session = Depends(get_session)) -> LoginDemoResponse:
    """Login demo: aceita username (admin, gestor_ap, gestor_unidade, acs1..5).

    Sem senha — é piloto. Em produção: SSO + token signing.
    """
    user = session.exec(select(User).where(User.username == payload.username)).first()
    if user is None or not user.ativo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido")
    assert user.id is not None
    token, expira = issue_token(user.id)
    log.info("auth.login", user=user.username, role=user.role.value)
    return LoginDemoResponse(
        access_token=token,
        expires_at=expira,
        user=UserOut(
            id=user.id,
            username=user.username,
            nome_display=user.nome_display,
            role=user.role,
            profissional_id=user.profissional_id,
            equipe_id=user.equipe_id,
            unidade_id=user.unidade_id,
            ap_id=user.ap_id,
        ),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Retorna o usuário autenticado."""
    assert user.id is not None
    return UserOut(
        id=user.id,
        username=user.username,
        nome_display=user.nome_display,
        role=user.role,
        profissional_id=user.profissional_id,
        equipe_id=user.equipe_id,
        unidade_id=user.unidade_id,
        ap_id=user.ap_id,
    )


@router.post("/logout", status_code=204)
def logout(
    user: User = Depends(get_current_user),
    authorization: str | None = Header(default=None),
) -> None:
    """Revoga o token corrente. Idempotente."""
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            revoke_token(parts[1])
    log.info("auth.logout", user=user.username)

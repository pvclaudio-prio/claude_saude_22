"""Endpoints de registros de visita.

Apenas usuários com papel ACS criam registros (gestores/admin só consultam).
Cada registro fica vinculado ao profissional logado e gera entrada na
auditoria. Edição parcial (PATCH) só pelo próprio autor do registro.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.core.security import apply_paciente_scope, get_current_user, require_roles
from app.db.models import Paciente, RegistroVisita, User, UserRole
from app.db.session import get_session
from app.schemas.registros import (
    RegistroVisitaIn,
    RegistroVisitaOut,
    RegistroVisitaPatch,
)
from app.services.registros import criar_registro, editar_registro, sugerir_ficha

router = APIRouter(prefix="/registros-visita", tags=["registros"])
log = get_logger("routers.registros")


def _to_out(r: RegistroVisita) -> RegistroVisitaOut:
    assert r.id is not None
    return RegistroVisitaOut(
        id=r.id,
        paciente_id=r.paciente_id,
        profissional_id=r.profissional_id,
        criado_em=r.criado_em,
        criado_por_user_id=r.criado_por_user_id,
        origem=r.origem,
        ficha_tipo=r.ficha_tipo,
        respostas=r.respostas,
        resumo=r.resumo,
        sinais_risco=list(r.sinais_risco),
        violencia=r.violencia,
        necessidades_especiais=list(r.necessidades_especiais),
        encaminhamentos=list(r.encaminhamentos),
        proxima_acao=r.proxima_acao,
        prazo_retorno=r.prazo_retorno,
        status=r.status,
        confianca_ia=r.confianca_ia,
        campos_baixa_confianca=list(r.campos_baixa_confianca),
    )


@router.post(
    "",
    response_model=RegistroVisitaOut,
    dependencies=[Depends(require_roles(UserRole.ACS))],
)
def criar(
    payload: RegistroVisitaIn,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RegistroVisitaOut:
    """Cria registro de visita. Apenas ACS pode chamar.

    Valida o paciente esteja no escopo do ACS antes de salvar.
    """
    q = select(Paciente).where(Paciente.id == payload.paciente_id)
    q = apply_paciente_scope(q, user)
    paciente = session.exec(q).first()
    if paciente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente fora do escopo.")

    try:
        reg = criar_registro(session, user=user, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _to_out(reg)


@router.get("/{registro_id}", response_model=RegistroVisitaOut)
def obter(
    registro_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RegistroVisitaOut:
    reg = session.get(RegistroVisita, registro_id)
    if reg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Escopo: ACS só vê os próprios; gestores/admin podem ver dentro de seu escopo de paciente
    if user.role is UserRole.ACS:
        if reg.profissional_id != user.profissional_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    else:
        # garante que o paciente está no escopo do usuário
        q = select(Paciente).where(Paciente.id == reg.paciente_id)
        q = apply_paciente_scope(q, user)
        if session.exec(q).first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return _to_out(reg)


@router.patch(
    "/{registro_id}",
    response_model=RegistroVisitaOut,
    dependencies=[Depends(require_roles(UserRole.ACS))],
)
def editar(
    registro_id: int,
    patch: RegistroVisitaPatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RegistroVisitaOut:
    reg = session.get(RegistroVisita, registro_id)
    if reg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if reg.profissional_id != user.profissional_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Não é autor do registro.")

    reg = editar_registro(session, user=user, registro=reg, patch=patch)
    return _to_out(reg)


@router.get("/by-paciente/{paciente_id}", response_model=list[RegistroVisitaOut])
def listar_por_paciente(
    paciente_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RegistroVisitaOut]:
    """Lista os registros de um paciente (respeita escopo)."""
    q = select(Paciente).where(Paciente.id == paciente_id)
    q = apply_paciente_scope(q, user)
    if session.exec(q).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    regs = session.exec(
        select(RegistroVisita)
        .where(RegistroVisita.paciente_id == paciente_id)
        .order_by(desc(RegistroVisita.criado_em))
    ).all()
    return [_to_out(r) for r in regs]


@router.get("/sugerir-ficha/{paciente_id}")
def sugerir(paciente_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    """Sugere o tipo de ficha mais provável para o paciente.

    Útil para o frontend pré-selecionar a ficha ao abrir o formulário.
    """
    q = select(Paciente).where(Paciente.id == paciente_id)
    q = apply_paciente_scope(q, user)
    p = session.exec(q).first()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"ficha_tipo": sugerir_ficha(p).value}

"""Endpoints de equipes, unidades, APs, bairros e profissionais."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.security import (
    apply_equipe_scope,
    apply_profissional_scope,
    get_current_user,
)
from app.db.models import AreaProgramatica, Bairro, Equipe, Profissional, Unidade, User
from app.db.session import get_session
from app.schemas.equipes import (
    AreaProgramaticaOut,
    BairroOut,
    EquipeOut,
    ProfissionalOut,
    UnidadeOut,
)

router = APIRouter(tags=["territorio"])


@router.get("/equipes", response_model=list[EquipeOut])
def listar_equipes(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[EquipeOut]:
    q = apply_equipe_scope(select(Equipe), user)
    rows = session.exec(q).all()
    return [
        EquipeOut(
            id=e.id,  # type: ignore[arg-type]
            hash_id=e.hash_id,
            nome_display=e.nome_display,
            unidade_id=e.unidade_id,
            ap_id=e.ap_id,
            bairro_id=e.bairro_id,
            sede_lat=e.sede_lat,
            sede_lon=e.sede_lon,
        )
        for e in rows
    ]


@router.get("/unidades", response_model=list[UnidadeOut])
def listar_unidades(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[UnidadeOut]:
    from app.db.models import UserRole

    q = select(Unidade)
    if user.role is UserRole.GESTOR_AP and user.ap_id is not None:
        q = q.where(Unidade.ap_id == user.ap_id)
    elif user.role is UserRole.GESTOR_UNIDADE and user.unidade_id is not None:
        q = q.where(Unidade.id == user.unidade_id)
    elif user.role is UserRole.ACS and user.unidade_id is not None:
        q = q.where(Unidade.id == user.unidade_id)
    elif user.role is UserRole.ADMIN:
        pass
    rows = session.exec(q).all()
    return [
        UnidadeOut(
            id=u.id,  # type: ignore[arg-type]
            hash_id=u.hash_id,
            nome_display=u.nome_display,
            ap_id=u.ap_id,
            bairro_id=u.bairro_id,
            centro_lat=u.centro_lat,
            centro_lon=u.centro_lon,
        )
        for u in rows
    ]


@router.get("/areas-programaticas", response_model=list[AreaProgramaticaOut])
def listar_aps(session: Session = Depends(get_session)) -> list[AreaProgramaticaOut]:
    """AP é visível para todos (territorialização básica)."""
    rows = session.exec(select(AreaProgramatica)).all()
    return [
        AreaProgramaticaOut(
            id=a.id,  # type: ignore[arg-type]
            nome=a.nome,
            derivado=a.derivado,
            centro_lat=a.centro_lat,
            centro_lon=a.centro_lon,
        )
        for a in rows
    ]


@router.get("/bairros", response_model=list[BairroOut])
def listar_bairros(session: Session = Depends(get_session)) -> list[BairroOut]:
    rows = session.exec(select(Bairro)).all()
    return [
        BairroOut(
            id=b.id,  # type: ignore[arg-type]
            nome=b.nome,
            ap_id=b.ap_id,
            derivado=b.derivado,
        )
        for b in rows
    ]


@router.get("/profissionais", response_model=list[ProfissionalOut])
def listar_profissionais(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ProfissionalOut]:
    q = apply_profissional_scope(select(Profissional), user)
    rows = session.exec(q).all()
    return [
        ProfissionalOut(
            id=p.id,  # type: ignore[arg-type]
            hash_id=p.hash_id,
            nome_display=p.nome_display,
            role=p.role,
            equipe_id=p.equipe_id,
            unidade_id=p.unidade_id,
            ap_id=p.ap_id,
            ativo=p.ativo,
        )
        for p in rows
    ]


@router.get("/profissionais/{prof_id}", response_model=ProfissionalOut)
def detalhar_profissional(
    prof_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProfissionalOut:
    q = apply_profissional_scope(select(Profissional).where(Profissional.id == prof_id), user)
    p = session.exec(q).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return ProfissionalOut(
        id=p.id,  # type: ignore[arg-type]
        hash_id=p.hash_id,
        nome_display=p.nome_display,
        role=p.role,
        equipe_id=p.equipe_id,
        unidade_id=p.unidade_id,
        ap_id=p.ap_id,
        ativo=p.ativo,
    )

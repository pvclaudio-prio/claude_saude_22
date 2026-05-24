"""Endpoints de pacientes — listagem, detalhe, timeline, risco.

Todos os endpoints aplicam **escopo por papel** via `apply_paciente_scope`.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlmodel import Session, select

from app.core.security import apply_paciente_scope, get_current_user, require_roles
from app.db.models import (
    EventoClinico,
    NivelRisco,
    Paciente,
    RegistroVisita,
    RiscoPaciente,
    User,
    UserRole,
    Visita,
)
from app.db.session import get_session
from app.schemas.pacientes import (
    EventoClinicoOut,
    PacienteDetalhe,
    PacienteResumo,
    TimelineItem,
    TimelinePaciente,
    VisitaOut,
)
from app.services.risk_score import calcular_score_paciente

router = APIRouter(prefix="/pacientes", tags=["pacientes"])


def _to_resumo(p: Paciente) -> PacienteResumo:
    assert p.id is not None
    return PacienteResumo(
        id=p.id,
        hash_id=p.hash_id,
        nome_display=p.nome_display,
        faixa_etaria=p.faixa_etaria,
        sexo=p.sexo,
        situacao_vulnerabilidade=p.situacao_vulnerabilidade,
        hipertenso=p.hipertenso,
        diabetico=p.diabetico,
        gestacao=p.gestacao,
        endereco_latitude=p.endereco_latitude,
        endereco_longitude=p.endereco_longitude,
        coordenada_outlier=p.coordenada_outlier,
        score_atual=p.score_atual,
        nivel_risco=p.nivel_risco,
        ultima_visita_em=p.ultima_visita_em,
        equipe_id=p.equipe_id,
        unidade_id=p.unidade_id,
        ap_id=p.ap_id,
        bairro_id=p.bairro_id,
    )


@router.get("", response_model=list[PacienteResumo])
def listar_pacientes(
    nivel: NivelRisco | None = Query(default=None),
    equipe_id: int | None = Query(default=None),
    unidade_id: int | None = Query(default=None),
    ap_id: int | None = Query(default=None),
    bairro_id: int | None = Query(default=None),
    gestacao: bool | None = Query(default=None),
    hipertenso: bool | None = Query(default=None),
    diabetico: bool | None = Query(default=None),
    vulnerabilidade: bool | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[PacienteResumo]:
    """Lista pacientes no escopo do usuário, com filtros opcionais."""
    q = select(Paciente)
    q = apply_paciente_scope(q, user)
    if nivel is not None:
        q = q.where(Paciente.nivel_risco == nivel)
    if equipe_id is not None:
        q = q.where(Paciente.equipe_id == equipe_id)
    if unidade_id is not None:
        q = q.where(Paciente.unidade_id == unidade_id)
    if ap_id is not None:
        q = q.where(Paciente.ap_id == ap_id)
    if bairro_id is not None:
        q = q.where(Paciente.bairro_id == bairro_id)
    if gestacao is not None:
        q = q.where(Paciente.gestacao == gestacao)
    if hipertenso is not None:
        q = q.where(Paciente.hipertenso == hipertenso)
    if diabetico is not None:
        q = q.where(Paciente.diabetico == diabetico)
    if vulnerabilidade is not None:
        q = q.where(Paciente.situacao_vulnerabilidade == vulnerabilidade)

    q = q.order_by(desc(Paciente.score_atual)).offset(offset).limit(limit)
    rows = session.exec(q).all()
    return [_to_resumo(p) for p in rows]


def _get_paciente_no_escopo(paciente_id: int, session: Session, user: User) -> Paciente:
    q = select(Paciente).where(Paciente.id == paciente_id)
    q = apply_paciente_scope(q, user)
    p = session.exec(q).first()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado")
    return p


@router.get("/{paciente_id}", response_model=PacienteDetalhe)
def detalhar_paciente(
    paciente_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PacienteDetalhe:
    p = _get_paciente_no_escopo(paciente_id, session, user)

    # Buscar fatores do último snapshot de risco (se houver)
    snap = session.exec(
        select(RiscoPaciente)
        .where(RiscoPaciente.paciente_id == p.id)
        .order_by(desc(RiscoPaciente.atualizado_em))
        .limit(1)
    ).first()
    fatores = snap.fatores if snap else []

    from app.services.registros import sugerir_ficha

    base = _to_resumo(p).model_dump()
    return PacienteDetalhe(
        **base,
        raca_cor=p.raca_cor,
        fatores_risco=fatores,
        ficha_sugerida=sugerir_ficha(p).value,
    )


@router.get("/{paciente_id}/timeline", response_model=TimelinePaciente)
def timeline_paciente(
    paciente_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TimelinePaciente:
    p = _get_paciente_no_escopo(paciente_id, session, user)
    assert p.id is not None

    itens: list[TimelineItem] = []

    visitas = session.exec(
        select(Visita).where(Visita.paciente_id == p.id).order_by(desc(Visita.data))
    ).all()
    for v in visitas:
        itens.append(
            TimelineItem(
                tipo="visita",
                data=v.data,
                rotulo="Visita do ACS",
                detalhes={"profissional_id": v.profissional_id, "ordem": v.ordem_visita_dia},
            )
        )

    eventos = session.exec(
        select(EventoClinico)
        .where(EventoClinico.paciente_id == p.id)
        .order_by(desc(EventoClinico.data_referencia))
    ).all()
    for e in eventos:
        rotulo = (
            "Urgência / emergência / internação"
            if e.tipo.value == "urgencia-emergencia-ou-internacao"
            else "Agendamento"
        )
        itens.append(
            TimelineItem(tipo="evento_clinico", data=e.data_referencia, rotulo=rotulo, detalhes={"tipo": e.tipo.value})
        )

    registros = session.exec(
        select(RegistroVisita)
        .where(RegistroVisita.paciente_id == p.id)
        .order_by(desc(RegistroVisita.criado_em))
    ).all()
    for r in registros:
        itens.append(
            TimelineItem(
                tipo="registro_visita",
                data=r.criado_em.date() if r.criado_em else date.today(),
                rotulo=f"Registro ({r.ficha_tipo.value})",
                detalhes={"resumo": r.resumo, "status": r.status.value, "origem": r.origem.value},
            )
        )

    itens.sort(key=lambda i: i.data, reverse=True)
    return TimelinePaciente(paciente_id=p.id, itens=itens)


@router.get("/{paciente_id}/eventos-clinicos", response_model=list[EventoClinicoOut])
def eventos_do_paciente(
    paciente_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[EventoClinicoOut]:
    p = _get_paciente_no_escopo(paciente_id, session, user)
    eventos = session.exec(
        select(EventoClinico)
        .where(EventoClinico.paciente_id == p.id)
        .order_by(desc(EventoClinico.data_referencia))
    ).all()
    return [
        EventoClinicoOut(id=e.id, paciente_id=e.paciente_id, tipo=e.tipo, data_referencia=e.data_referencia)  # type: ignore[arg-type]
        for e in eventos
    ]


@router.get("/{paciente_id}/visitas", response_model=list[VisitaOut])
def visitas_do_paciente(
    paciente_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[VisitaOut]:
    p = _get_paciente_no_escopo(paciente_id, session, user)
    visitas = session.exec(
        select(Visita).where(Visita.paciente_id == p.id).order_by(desc(Visita.data))
    ).all()
    return [
        VisitaOut(
            id=v.id,  # type: ignore[arg-type]
            paciente_id=v.paciente_id,
            profissional_id=v.profissional_id,
            data=v.data,
            ordem_visita_dia=v.ordem_visita_dia,
        )
        for v in visitas
    ]


@router.post("/recalcular-risco", dependencies=[Depends(require_roles(UserRole.ADMIN))])
def recalcular_risco(session: Session = Depends(get_session)) -> dict[str, int]:
    """Recalcula score de TODOS os pacientes — admin-only (operação pesada)."""
    from app.services.risk_score import recalcular_todos

    n = recalcular_todos(session)
    return {"processados": n}

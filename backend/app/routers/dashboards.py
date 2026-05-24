"""Endpoints de dashboards e mapa.

Todos os endpoints respeitam o escopo do usuário (ACS, gestor unidade, AP, admin)
via `apply_paciente_scope`.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func
from sqlmodel import Session, select

from app.core.security import apply_paciente_scope, get_current_user, apply_equipe_scope
from app.db.models import (
    Equipe,
    EventoClinico,
    NivelRisco,
    Paciente,
    RiscoPaciente,
    TipoEventoClinico,
    Unidade,
    User,
    UserRole,
    Visita,
)
from app.db.session import get_session
from app.schemas.dashboards import (
    HeatmapResponse,
    HeatmapTipo,
    ItemRanking,
    KpisDashboard,
    MapaResponse,
    PontoPaciente,
    RankingPacientes,
)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _label_escopo(user: User, session: Session) -> str:
    if user.role is UserRole.ADMIN:
        return "Admin (todos)"
    if user.role is UserRole.GESTOR_AP and user.ap_id is not None:
        return f"AP #{user.ap_id}"
    if user.role is UserRole.GESTOR_UNIDADE and user.unidade_id is not None:
        u = session.get(Unidade, user.unidade_id)
        return f"Unidade {u.nome_display}" if u else "Unidade"
    if user.role is UserRole.ACS and user.equipe_id is not None:
        e = session.get(Equipe, user.equipe_id)
        return f"Equipe {e.nome_display}" if e else "Equipe"
    return "Sem escopo"


def _scope_subq(user: User):
    """Subquery com os IDs do escopo — evita `IN (...)` com milhares de variáveis."""
    return apply_paciente_scope(select(Paciente.id), user).subquery()


@router.get("/kpis", response_model=KpisDashboard)
def kpis(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KpisDashboard:
    hoje = date.today()
    scope_sq = _scope_subq(user)

    def _count(extra_filter) -> int:
        q = select(func.count(Paciente.id)).where(Paciente.id.in_(select(scope_sq)))
        if extra_filter is not None:
            q = q.where(extra_filter)
        return int(session.exec(q).one() or 0)

    total = _count(None)
    if total == 0:
        return KpisDashboard(
            pacientes_total=0, pacientes_criticos=0, pacientes_alto_risco=0,
            pacientes_vulneraveis=0, gestantes=0, hipertensos=0, diabeticos=0,
            idosos=0, criancas_0_6=0, sem_visita_90d=0, sem_visita_180d=0,
            visitas_ultimo_mes=0, eventos_urgencia_30d=0, score_medio=0.0,
            escopo=_label_escopo(user, session),
        )

    criticos = _count(Paciente.nivel_risco == NivelRisco.CRITICO)
    altos = _count(Paciente.nivel_risco == NivelRisco.ALTO)
    vuln = _count(Paciente.situacao_vulnerabilidade == True)  # noqa: E712
    gest = _count(Paciente.gestacao == True)  # noqa: E712
    has = _count(Paciente.hipertenso == True)  # noqa: E712
    dm = _count(Paciente.diabetico == True)  # noqa: E712
    idosos = _count(Paciente.faixa_etaria == "66+")
    criancas = _count(Paciente.faixa_etaria == "0-6")

    sem90 = _count(Paciente.ultima_visita_em < hoje - timedelta(days=90))  # type: ignore[operator]
    sem180 = _count(Paciente.ultima_visita_em < hoje - timedelta(days=180))  # type: ignore[operator]

    n_visitas_mes = session.exec(
        select(func.count(Visita.id))
        .where(Visita.paciente_id.in_(select(scope_sq)))
        .where(Visita.data >= hoje - timedelta(days=30))
    ).one() or 0

    n_urg = session.exec(
        select(func.count(EventoClinico.id))
        .where(EventoClinico.paciente_id.in_(select(scope_sq)))
        .where(EventoClinico.tipo == TipoEventoClinico.URGENCIA)
        .where(EventoClinico.data_referencia >= hoje - timedelta(days=30))
    ).one() or 0

    score_medio = float(session.exec(
        select(func.avg(Paciente.score_atual)).where(Paciente.id.in_(select(scope_sq)))
    ).one() or 0.0)

    return KpisDashboard(
        pacientes_total=total,
        pacientes_criticos=criticos,
        pacientes_alto_risco=altos,
        pacientes_vulneraveis=vuln,
        gestantes=gest,
        hipertensos=has,
        diabeticos=dm,
        idosos=idosos,
        criancas_0_6=criancas,
        sem_visita_90d=sem90,
        sem_visita_180d=sem180,
        visitas_ultimo_mes=int(n_visitas_mes),
        eventos_urgencia_30d=int(n_urg),
        score_medio=round(score_medio, 2),
        escopo=_label_escopo(user, session),
    )


@router.get("/mapa", response_model=MapaResponse)
def mapa(
    nivel: NivelRisco | None = Query(default=None),
    limit: int = Query(default=500, ge=10, le=5000),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MapaResponse:
    """Retorna marcadores individuais (com cap) + sedes."""
    q = select(Paciente).where(Paciente.coordenada_outlier == False)  # noqa: E712
    q = apply_paciente_scope(q, user)
    if nivel is not None:
        q = q.where(Paciente.nivel_risco == nivel)

    total = session.exec(select(func.count()).select_from(q.subquery())).one() or 0

    q_ord = q.order_by(desc(Paciente.score_atual)).limit(limit)
    rows = session.exec(q_ord).all()
    pacientes = [
        PontoPaciente(
            paciente_id=p.id,  # type: ignore[arg-type]
            lat=p.endereco_latitude,
            lon=p.endereco_longitude,
            nivel_risco=p.nivel_risco,
            nome_display=p.nome_display,
        )
        for p in rows
    ]

    # Sedes — equipes no escopo
    sedes_equipes = []
    for e in session.exec(apply_equipe_scope(select(Equipe), user)).all():
        sedes_equipes.append({
            "equipe_id": e.id, "nome": e.nome_display, "lat": e.sede_lat, "lon": e.sede_lon,
        })

    # Sedes de unidades
    if user.role is UserRole.ADMIN:
        unidades = session.exec(select(Unidade)).all()
    elif user.role is UserRole.GESTOR_AP and user.ap_id is not None:
        unidades = session.exec(select(Unidade).where(Unidade.ap_id == user.ap_id)).all()
    elif user.role is UserRole.GESTOR_UNIDADE and user.unidade_id is not None:
        unidades = session.exec(select(Unidade).where(Unidade.id == user.unidade_id)).all()
    elif user.role is UserRole.ACS and user.unidade_id is not None:
        unidades = session.exec(select(Unidade).where(Unidade.id == user.unidade_id)).all()
    else:
        unidades = []
    sedes_unidades = [
        {"unidade_id": u.id, "nome": u.nome_display, "lat": u.centro_lat, "lon": u.centro_lon}
        for u in unidades if u.centro_lat is not None and u.centro_lon is not None
    ]

    return MapaResponse(
        pacientes=pacientes,
        sedes_equipes=sedes_equipes,
        sedes_unidades=sedes_unidades,
        total_no_escopo=int(total),
        truncado_em=limit if int(total) > limit else None,
    )


@router.get("/heatmap", response_model=HeatmapResponse)
def heatmap(
    tipo: HeatmapTipo = Query(...),
    limit: int = Query(default=2000, ge=10, le=10000),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> HeatmapResponse:
    """Pontos (lat, lon, intensidade) para um heatmap.

    - vulnerabilidade: peso 1.0 para pacientes vulneráveis
    - urgencia: peso 1.0 para pacientes com evento de urgência <90d
    - sem_visita: peso 1.0 para pacientes sem visita >180d
    """
    q = select(Paciente).where(Paciente.coordenada_outlier == False)  # noqa: E712
    q = apply_paciente_scope(q, user)

    hoje = date.today()
    pontos: list[tuple[float, float, float]] = []

    if tipo == "vulnerabilidade":
        q = q.where(Paciente.situacao_vulnerabilidade == True).limit(limit)  # noqa: E712
        for p in session.exec(q).all():
            pontos.append((p.endereco_latitude, p.endereco_longitude, 1.0))
    elif tipo == "urgencia":
        scope_sq = apply_paciente_scope(select(Paciente.id), user).subquery()
        urg_sq = (
            select(EventoClinico.paciente_id)
            .where(EventoClinico.paciente_id.in_(select(scope_sq)))
            .where(EventoClinico.tipo == TipoEventoClinico.URGENCIA)
            .where(EventoClinico.data_referencia >= hoje - timedelta(days=90))
        )
        q = q.where(Paciente.id.in_(urg_sq)).limit(limit)  # type: ignore[attr-defined]
        for p in session.exec(q).all():
            pontos.append((p.endereco_latitude, p.endereco_longitude, 1.0))
    elif tipo == "sem_visita":
        q = q.where(Paciente.ultima_visita_em < hoje - timedelta(days=180)).limit(limit)  # type: ignore[operator]
        for p in session.exec(q).all():
            pontos.append((p.endereco_latitude, p.endereco_longitude, 1.0))

    return HeatmapResponse(tipo=tipo, pontos=pontos, total=len(pontos))


@router.get("/ranking-pacientes", response_model=RankingPacientes)
def ranking_pacientes(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RankingPacientes:
    """Top-N pacientes de maior risco no escopo."""
    q = select(Paciente)
    q = apply_paciente_scope(q, user)
    q = q.order_by(desc(Paciente.score_atual)).limit(limit)
    rows = session.exec(q).all()

    items: list[ItemRanking] = []
    for p in rows:
        snap = session.exec(
            select(RiscoPaciente)
            .where(RiscoPaciente.paciente_id == p.id)
            .order_by(desc(RiscoPaciente.atualizado_em))
            .limit(1)
        ).first()
        motivos = [f.get("descricao", "") for f in (snap.fatores if snap else [])][:3]
        items.append(ItemRanking(
            paciente_id=p.id,  # type: ignore[arg-type]
            nome_display=p.nome_display,
            score=p.score_atual or 0.0,
            nivel_risco=p.nivel_risco,
            ultima_visita_em=p.ultima_visita_em,
            motivos=motivos,
        ))
    return RankingPacientes(items=items, escopo=_label_escopo(user, session))

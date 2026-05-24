"""Endpoints de relatórios — dados em JSON para o frontend renderizar/imprimir."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.core.security import apply_paciente_scope, get_current_user, require_roles
from app.db.models import (
    NivelRisco,
    Paciente,
    Profissional,
    RiscoPaciente,
    User,
    UserRole,
)
from app.db.session import get_session
from app.schemas.dashboards import RelatorioACSDia, RelatorioGestor
from app.services.planner import PlannerConfig, gerar_rota_dia

router = APIRouter(prefix="/relatorios", tags=["relatorios"])
log = get_logger("routers.relatorios")


@router.get("/acs-dia", response_model=RelatorioACSDia)
def relatorio_acs_dia(
    data: date | None = Query(default=None, description="Default: hoje"),
    profissional_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RelatorioACSDia:
    if user.role is UserRole.ACS:
        if user.profissional_id is None:
            raise HTTPException(403, "Sem profissional vinculado")
        pid = user.profissional_id
    else:
        if profissional_id is None:
            raise HTTPException(400, "Forneça profissional_id (gestores/admin)")
        pid = profissional_id

    prof = session.get(Profissional, pid)
    if prof is None:
        raise HTTPException(404, "Profissional não encontrado")

    d = data or date.today()
    rota = gerar_rota_dia(session, pid, d, PlannerConfig())

    # Pacientes críticos da rota com alertas (motivos)
    criticos = []
    for m in rota.motivos:
        pacote = m.copy()
        p = session.get(Paciente, m["paciente_id"])
        if p and p.nivel_risco in (NivelRisco.ALTO, NivelRisco.CRITICO):
            criticos.append({
                "paciente_id": p.id,
                "nome_display": p.nome_display,
                "nivel_risco": p.nivel_risco.value,
                "motivos": pacote.get("motivos", []),
            })

    totais = {
        "visitas_planejadas": len(rota.paciente_ids),
        "criticos": sum(1 for c in criticos if c["nivel_risco"] == "critico"),
        "altos": sum(1 for c in criticos if c["nivel_risco"] == "alto"),
        "distancia_km": rota.distancia_total_km,
    }

    return RelatorioACSDia(
        profissional_id=pid,
        profissional_nome=prof.nome_display,
        equipe_id=prof.equipe_id,
        data=d,
        gerado_em=datetime.now(UTC).isoformat(),
        rota={
            "data": d.isoformat(),
            "paciente_ids": rota.paciente_ids,
            "motivos": rota.motivos,
            "componentes": rota.componentes,
            "distancia_total_km": rota.distancia_total_km,
        },
        pacientes_criticos_alertas=criticos,
        totais=totais,
    )


@router.get(
    "/gestor-periodo",
    response_model=RelatorioGestor,
    dependencies=[Depends(require_roles(UserRole.GESTOR_UNIDADE, UserRole.GESTOR_AP, UserRole.ADMIN))],
)
def relatorio_gestor(
    inicio: date,
    fim: date,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RelatorioGestor:
    if fim < inicio:
        raise HTTPException(400, "fim < inicio")

    from sqlalchemy import func
    scope_sq = apply_paciente_scope(select(Paciente.id), user).subquery()

    pacientes_total = int(session.exec(
        select(func.count(Paciente.id)).where(Paciente.id.in_(select(scope_sq)))
    ).one() or 0)
    if not pacientes_total:
        raise HTTPException(404, "Sem pacientes no escopo")

    totais = {
        "pacientes": pacientes_total,
        "criticos": int(session.exec(
            select(func.count(Paciente.id))
            .where(Paciente.id.in_(select(scope_sq)))
            .where(Paciente.nivel_risco == NivelRisco.CRITICO)
        ).one() or 0),
        "altos": int(session.exec(
            select(func.count(Paciente.id))
            .where(Paciente.id.in_(select(scope_sq)))
            .where(Paciente.nivel_risco == NivelRisco.ALTO)
        ).one() or 0),
    }

    # Risco por equipe — agregação por equipe_id
    rows_equipe = session.exec(
        select(Paciente.equipe_id, func.count(Paciente.id))
        .where(Paciente.id.in_(select(scope_sq)))
        .group_by(Paciente.equipe_id)
    ).all()
    risco_por_equipe: dict[int, dict] = {}
    for equipe_id, n_pac in rows_equipe:
        risco_por_equipe[equipe_id or 0] = {
            "equipe_id": equipe_id or 0, "pacientes": int(n_pac),
            "criticos": 0, "altos": 0, "score_medio": 0.0,
        }

    rows_crit = session.exec(
        select(Paciente.equipe_id, func.count(Paciente.id))
        .where(Paciente.id.in_(select(scope_sq)))
        .where(Paciente.nivel_risco == NivelRisco.CRITICO)
        .group_by(Paciente.equipe_id)
    ).all()
    for eid, n in rows_crit:
        if (eid or 0) in risco_por_equipe:
            risco_por_equipe[eid or 0]["criticos"] = int(n)

    rows_alto = session.exec(
        select(Paciente.equipe_id, func.count(Paciente.id))
        .where(Paciente.id.in_(select(scope_sq)))
        .where(Paciente.nivel_risco == NivelRisco.ALTO)
        .group_by(Paciente.equipe_id)
    ).all()
    for eid, n in rows_alto:
        if (eid or 0) in risco_por_equipe:
            risco_por_equipe[eid or 0]["altos"] = int(n)

    rows_score = session.exec(
        select(Paciente.equipe_id, func.avg(Paciente.score_atual))
        .where(Paciente.id.in_(select(scope_sq)))
        .group_by(Paciente.equipe_id)
    ).all()
    for eid, score in rows_score:
        if (eid or 0) in risco_por_equipe:
            risco_por_equipe[eid or 0]["score_medio"] = round(float(score or 0.0), 2)

    riscos = sorted(risco_por_equipe.values(), key=lambda x: x["criticos"], reverse=True)

    # Top-15 pacientes críticos
    rows = session.exec(
        select(Paciente).where(Paciente.id.in_(select(scope_sq)))
        .order_by(desc(Paciente.score_atual)).limit(15)
    ).all()
    criticos = []
    for p in rows:
        snap = session.exec(
            select(RiscoPaciente)
            .where(RiscoPaciente.paciente_id == p.id)
            .order_by(desc(RiscoPaciente.atualizado_em))
            .limit(1)
        ).first()
        criticos.append({
            "paciente_id": p.id,
            "nome_display": p.nome_display,
            "score": p.score_atual,
            "nivel_risco": p.nivel_risco.value if p.nivel_risco else None,
            "ultima_visita_em": p.ultima_visita_em.isoformat() if p.ultima_visita_em else None,
            "motivos": [f.get("descricao", "") for f in (snap.fatores if snap else [])][:3],
        })

    # Escopo textual
    if user.role is UserRole.ADMIN:
        escopo = "Admin (todos)"
    elif user.role is UserRole.GESTOR_AP:
        escopo = f"AP #{user.ap_id}"
    else:
        escopo = f"Unidade #{user.unidade_id}"

    return RelatorioGestor(
        escopo=escopo,
        inicio=inicio,
        fim=fim,
        gerado_em=datetime.now(UTC).isoformat(),
        totais=totais,
        riscos_por_equipe=riscos[:20],
        pacientes_criticos=criticos,
        alertas_principais=[
            {"tipo": "criticos", "valor": totais["criticos"]},
            {"tipo": "altos", "valor": totais["altos"]},
        ],
    )

"""Endpoints de gestão — visões agregadas por equipe e por ACS.

Acesso restrito a: gestor_unidade, gestor_ap, admin.
ACS NÃO tem acesso (a aba é escondida no frontend e o backend bloqueia 403).
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlmodel import Session, select

from app.core.security import (
    apply_equipe_scope,
    apply_paciente_scope,
    apply_profissional_scope,
    get_current_user,
    require_roles,
)
from app.db.models import (
    Equipe,
    NivelRisco,
    Paciente,
    Profissional,
    User,
    UserRole,
    Visita,
)
from app.db.session import get_session

router = APIRouter(
    prefix="/gestao",
    tags=["gestao"],
    dependencies=[Depends(require_roles(UserRole.GESTOR_UNIDADE, UserRole.GESTOR_AP, UserRole.ADMIN))],
)


@router.get("/equipes")
def equipes_consolidado(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """KPIs consolidados por equipe no escopo do gestor."""
    equipes = session.exec(apply_equipe_scope(select(Equipe), user)).all()
    hoje = date.today()
    saida: list[dict] = []
    for e in equipes:
        # contagem por nível
        n_pac = int(session.exec(
            select(func.count(Paciente.id)).where(Paciente.equipe_id == e.id)
        ).one() or 0)
        if n_pac == 0:
            saida.append({
                "equipe_id": e.id, "nome": e.nome_display, "unidade_id": e.unidade_id,
                "ap_id": e.ap_id, "n_pacientes": 0, "n_criticos": 0, "n_altos": 0,
                "score_medio": 0.0, "sem_visita_180d": 0, "visitas_30d": 0,
                "n_profissionais": 0,
            })
            continue
        n_crit = int(session.exec(
            select(func.count(Paciente.id))
            .where(Paciente.equipe_id == e.id)
            .where(Paciente.nivel_risco == NivelRisco.CRITICO)
        ).one() or 0)
        n_alto = int(session.exec(
            select(func.count(Paciente.id))
            .where(Paciente.equipe_id == e.id)
            .where(Paciente.nivel_risco == NivelRisco.ALTO)
        ).one() or 0)
        score_medio = float(session.exec(
            select(func.avg(Paciente.score_atual)).where(Paciente.equipe_id == e.id)
        ).one() or 0.0)
        sem_visita_180 = int(session.exec(
            select(func.count(Paciente.id))
            .where(Paciente.equipe_id == e.id)
            .where(Paciente.ultima_visita_em < hoje - timedelta(days=180))  # type: ignore[operator]
        ).one() or 0)
        visitas_30d = int(session.exec(
            select(func.count(Visita.id))
            .where(Visita.paciente_id.in_(  # type: ignore[attr-defined]
                select(Paciente.id).where(Paciente.equipe_id == e.id)
            ))
            .where(Visita.data >= hoje - timedelta(days=30))
        ).one() or 0)
        n_prof = int(session.exec(
            select(func.count(Profissional.id)).where(Profissional.equipe_id == e.id)
        ).one() or 0)
        saida.append({
            "equipe_id": e.id, "nome": e.nome_display, "unidade_id": e.unidade_id,
            "ap_id": e.ap_id,
            "sede_lat": e.sede_lat, "sede_lon": e.sede_lon,
            "n_pacientes": n_pac,
            "n_criticos": n_crit,
            "n_altos": n_alto,
            "score_medio": round(score_medio, 2),
            "sem_visita_180d": sem_visita_180,
            "visitas_30d": visitas_30d,
            "n_profissionais": n_prof,
        })

    # Ordena por críticos desc
    saida.sort(key=lambda r: r["n_criticos"], reverse=True)
    return saida


@router.get("/acs")
def acs_consolidado(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    limit: int = 200,
) -> list[dict]:
    """KPIs consolidados por ACS no escopo do gestor."""
    profs = session.exec(
        apply_profissional_scope(select(Profissional), user).limit(limit)
    ).all()
    hoje = date.today()
    saida: list[dict] = []
    for p in profs:
        # pacientes da equipe + visitados por ele
        n_visitas_total = int(session.exec(
            select(func.count(Visita.id)).where(Visita.profissional_id == p.id)
        ).one() or 0)
        n_visitas_30d = int(session.exec(
            select(func.count(Visita.id))
            .where(Visita.profissional_id == p.id)
            .where(Visita.data >= hoje - timedelta(days=30))
        ).one() or 0)
        pacientes_unicos = int(session.exec(
            select(func.count(func.distinct(Visita.paciente_id)))
            .where(Visita.profissional_id == p.id)
        ).one() or 0)
        saida.append({
            "profissional_id": p.id,
            "nome": p.nome_display,
            "equipe_id": p.equipe_id,
            "unidade_id": p.unidade_id,
            "ap_id": p.ap_id,
            "n_visitas_total": n_visitas_total,
            "n_visitas_30d": n_visitas_30d,
            "pacientes_unicos": pacientes_unicos,
            "ativo": p.ativo,
        })

    saida.sort(key=lambda r: r["n_visitas_total"], reverse=True)
    return saida

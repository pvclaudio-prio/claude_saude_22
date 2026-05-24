"""Seed de usuários demo para o login (1 admin + gestores + ACSs).

Estratégia: depois da ingestão dos parquets, escolhemos:
- 1 admin (sem vínculo a equipe/unidade/AP),
- 1 gestor de AP (vinculado à AP-01),
- 1 gestor de unidade (vinculado à unidade com mais pacientes),
- 5 ACSs reais escolhidos entre os profissionais com mais visitas.

Os usernames são determinísticos (`acs1..acs5`, `gestor_unidade`, etc.) para
permitir login demo sem digitar hash.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.db.session import engine
from app.db.models import (
    AreaProgramatica,
    Equipe,
    Profissional,
    Unidade,
    User,
    UserRole,
    Visita,
)

log = get_logger("importers.seed_users")


def seed_demo_users(n_acs: int = 5) -> dict[str, int]:
    """Cria usuários demo. Retorna mapa username→user_id."""
    created: dict[str, int] = {}

    with Session(engine) as session:
        # 1) admin
        admin = User(username="admin", nome_display="Admin Saúde RJ", role=UserRole.ADMIN)
        session.add(admin)
        session.flush()
        assert admin.id is not None
        created["admin"] = admin.id

        # 2) gestor AP — pega AP-01
        ap = session.exec(select(AreaProgramatica).order_by(AreaProgramatica.id)).first()
        if ap is not None:
            gap = User(
                username="gestor_ap",
                nome_display=f"Gestor {ap.nome}",
                role=UserRole.GESTOR_AP,
                ap_id=ap.id,
            )
            session.add(gap)
            session.flush()
            assert gap.id is not None
            created["gestor_ap"] = gap.id

        # 3) gestor de unidade — unidade com mais pacientes
        from app.db.models import Paciente

        row = session.exec(
            select(Paciente.unidade_id, func.count(Paciente.id).label("n"))
            .where(Paciente.unidade_id.is_not(None))  # type: ignore[attr-defined]
            .group_by(Paciente.unidade_id)
            .order_by(func.count(Paciente.id).desc())
            .limit(1)
        ).first()
        if row is not None:
            unidade_id, _ = row
            unidade = session.get(Unidade, unidade_id)
            gu = User(
                username="gestor_unidade",
                nome_display=f"Gestor {unidade.nome_display}" if unidade else "Gestor Unidade",
                role=UserRole.GESTOR_UNIDADE,
                unidade_id=unidade_id,
                ap_id=unidade.ap_id if unidade else None,
            )
            session.add(gu)
            session.flush()
            assert gu.id is not None
            created["gestor_unidade"] = gu.id

        # 4) ACSs — os com mais visitas
        rows = session.exec(
            select(Visita.profissional_id, func.count(Visita.id).label("n"))
            .group_by(Visita.profissional_id)
            .order_by(func.count(Visita.id).desc())
            .limit(n_acs)
        ).all()

        for idx, (prof_id, _n) in enumerate(rows, start=1):
            prof = session.get(Profissional, prof_id)
            if prof is None:
                continue
            equipe = session.get(Equipe, prof.equipe_id) if prof.equipe_id else None
            user = User(
                username=f"acs{idx}",
                nome_display=prof.nome_display,
                role=UserRole.ACS,
                profissional_id=prof.id,
                equipe_id=prof.equipe_id,
                unidade_id=prof.unidade_id,
                ap_id=prof.ap_id or (equipe.ap_id if equipe else None),
            )
            session.add(user)
            session.flush()
            assert user.id is not None
            created[user.username] = user.id

        session.commit()

    log.info("seed_users.done", criados=list(created.keys()))
    return created

"""Seed do planner — pré-gera 7 dias de rota para usuários demo.

Garante que qualquer login (admin, gestor, acs1..5) já encontra rota pronta.

Estratégia:
- Para cada ACS demo, gera 6 dias (segunda → sábado a partir de hoje).
- Gestores/admin não têm rota própria; o frontend resolve qual ACS exibir.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app.core.logging import get_logger
from app.db.models import User, UserRole
from app.db.session import engine
from app.services.planner import (
    PlannerConfig,
    gerar_rota_periodo,
    persistir_rota,
)

log = get_logger("importers.seed_planner")


def seed_planner_acs_demo(dias: int = 6) -> int:
    """Gera planner para os ACSs demo. Retorna número total de rotas-dia geradas.

    Args:
        dias: quantos dias úteis a partir de hoje (default 6 = uma semana sem domingo).
    """
    inicio = date.today()
    fim = inicio + timedelta(days=dias)

    total = 0
    with Session(engine) as session:
        acsuarios = session.exec(
            select(User).where(User.role == UserRole.ACS).where(User.profissional_id.is_not(None))  # type: ignore[union-attr]
        ).all()
        log.info("seed_planner.start", n_acs=len(acsuarios), inicio=str(inicio), fim=str(fim))

        cfg = PlannerConfig()
        for u in acsuarios:
            assert u.profissional_id is not None
            rotas = gerar_rota_periodo(session, u.profissional_id, inicio, fim, cfg)
            for r in rotas:
                persistir_rota(session, r)
                total += 1

    log.info("seed_planner.done", total=total)
    return total

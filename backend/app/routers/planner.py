"""Endpoints do planner.

* ``/planner/dia``       — rota de um dia para o ACS (default: hoje)
* ``/planner/semana``    — 7 dias a partir de hoje (segunda → sábado)
* ``/planner/periodo``   — janela [inicio, fim]
* ``/planner/recalcular`` — força nova geração + persistência

Em todos os casos, se já existe uma ``RotaPlanejada`` para (profissional, data),
ela é usada. Caso contrário, o planner gera **on-demand** — isso garante que
qualquer usuário que logue tenha rota imediatamente, mesmo se o seed não tiver
rodado para o dia atual.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.core.security import get_current_user, require_roles
from app.db.models import (
    Paciente,
    Profissional,
    RotaPlanejada,
    User,
    UserRole,
)
from app.db.session import get_session
from app.schemas.planner import (
    ItemRota,
    RecalcularRequest,
    RotaDia,
    RotaPeriodo,
    RotaSemana,
)
from app.services.planner import (
    PlannerConfig,
    gerar_rota_dia,
    gerar_rota_periodo,
    persistir_rota,
)

router = APIRouter(prefix="/planner", tags=["planner"])
log = get_logger("routers.planner")


def _resolver_profissional_id(user: User, override: int | None) -> int:
    """Resolve o profissional alvo do planner com base no papel."""
    if user.role is UserRole.ACS:
        if user.profissional_id is None:
            raise HTTPException(403, "ACS sem profissional vinculado")
        # ACS só vê o próprio planner — ignora qualquer override.
        return user.profissional_id
    # Gestores e admin podem ver de qualquer profissional via query param.
    if override is None:
        raise HTTPException(400, "Forneça `profissional_id` (gestores/admin)")
    return override


def _carregar_ou_gerar_rota(
    session: Session,
    profissional_id: int,
    data: date,
    cfg: PlannerConfig,
    persistir: bool,
) -> RotaDia:
    """Tenta pegar rota persistida; se não houver, gera e (opcionalmente) salva."""
    persistida = session.exec(
        select(RotaPlanejada)
        .where(RotaPlanejada.profissional_id == profissional_id)
        .where(RotaPlanejada.data == data)
    ).first()

    if persistida is not None and not persistir:
        return _rota_planejada_para_dto(session, persistida, profissional_id)

    resultado = gerar_rota_dia(session, profissional_id, data, cfg)
    if persistir:
        persistir_rota(session, resultado)

    prof = session.get(Profissional, profissional_id)
    pacs = _pacientes_por_id(session, resultado.paciente_ids)
    itens = _build_itens(resultado, pacs)
    return RotaDia(
        profissional_id=profissional_id,
        profissional_nome=prof.nome_display if prof else None,
        equipe_id=prof.equipe_id if prof else None,
        data=data,
        itens=itens,
        distancia_total_km=resultado.distancia_total_km,
        pesos={
            "risco": cfg.w_risco,
            "proximidade": cfg.w_proximidade,
            "recencia": cfg.w_recencia,
        },
        gerado_em=datetime.now(UTC).isoformat(),
    )


def _pacientes_por_id(session: Session, ids: list[int]) -> dict[int, Paciente]:
    if not ids:
        return {}
    rows = session.exec(select(Paciente).where(Paciente.id.in_(ids))).all()  # type: ignore[attr-defined]
    return {p.id: p for p in rows if p.id is not None}


def _build_itens(resultado, pacs: dict[int, Paciente]) -> list[ItemRota]:
    componentes_map = {c["paciente_id"]: c for c in resultado.componentes}
    motivos_map = {m["paciente_id"]: m for m in resultado.motivos}
    itens: list[ItemRota] = []
    for ordem, pid in enumerate(resultado.paciente_ids, start=1):
        p = pacs.get(pid)
        if p is None:
            continue
        comp = componentes_map.get(pid, {})
        mot = motivos_map.get(pid, {})
        itens.append(
            ItemRota(
                ordem=ordem,
                paciente_id=pid,
                nome_display=p.nome_display,
                score_combinado=mot.get("score_combinado", 0.0),
                nivel_risco=p.nivel_risco,
                score_risco=p.score_atual,
                distancia_km=comp.get("distancia_km", 0.0),
                dias_sem_visita=comp.get("dias_sem_visita"),
                componentes={
                    "s_risco": comp.get("s_risco", 0.0),
                    "s_proximidade": comp.get("s_proximidade", 0.0),
                    "s_recencia": comp.get("s_recencia", 0.0),
                },
                motivos=mot.get("motivos", []),
                latitude=p.endereco_latitude,
                longitude=p.endereco_longitude,
            )
        )
    return itens


def _rota_planejada_para_dto(
    session: Session, rota: RotaPlanejada, profissional_id: int
) -> RotaDia:
    """Converte uma RotaPlanejada persistida em DTO (refresca dados do paciente)."""
    pacs = _pacientes_por_id(session, rota.paciente_ids)
    prof = session.get(Profissional, profissional_id)
    itens: list[ItemRota] = []
    motivos_map = {m["paciente_id"]: m for m in (rota.motivos or [])}
    for ordem, pid in enumerate(rota.paciente_ids, start=1):
        p = pacs.get(pid)
        if p is None:
            continue
        mot = motivos_map.get(pid, {})
        itens.append(
            ItemRota(
                ordem=ordem,
                paciente_id=pid,
                nome_display=p.nome_display,
                score_combinado=mot.get("score_combinado", 0.0),
                nivel_risco=p.nivel_risco,
                score_risco=p.score_atual,
                distancia_km=0.0,
                dias_sem_visita=None,
                componentes={},
                motivos=mot.get("motivos", []),
                latitude=p.endereco_latitude,
                longitude=p.endereco_longitude,
            )
        )
    return RotaDia(
        profissional_id=profissional_id,
        profissional_nome=prof.nome_display if prof else None,
        equipe_id=prof.equipe_id if prof else None,
        data=rota.data,
        itens=itens,
        distancia_total_km=0.0,
        pesos={"risco": 0.5, "proximidade": 0.3, "recencia": 0.2},
        gerado_em=rota.gerado_em.isoformat() if rota.gerado_em else datetime.now(UTC).isoformat(),
    )


@router.get("/dia", response_model=RotaDia)
def planner_dia(
    data: date | None = Query(default=None, description="Default: hoje"),
    profissional_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RotaDia:
    pid = _resolver_profissional_id(user, profissional_id)
    return _carregar_ou_gerar_rota(session, pid, data or date.today(), PlannerConfig(), persistir=False)


@router.get("/semana", response_model=RotaSemana)
def planner_semana(
    inicio: date | None = Query(default=None, description="Default: hoje"),
    profissional_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RotaSemana:
    pid = _resolver_profissional_id(user, profissional_id)
    inicio = inicio or date.today()
    fim = inicio + timedelta(days=6)
    dias: list[RotaDia] = []
    cfg = PlannerConfig()
    for offset in range(7):
        d = inicio + timedelta(days=offset)
        if d.weekday() == 6:  # domingo
            continue
        dias.append(_carregar_ou_gerar_rota(session, pid, d, cfg, persistir=False))
    return RotaSemana(profissional_id=pid, dias=dias)


@router.get("/periodo", response_model=RotaPeriodo)
def planner_periodo(
    inicio: date,
    fim: date,
    profissional_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RotaPeriodo:
    pid = _resolver_profissional_id(user, profissional_id)
    if fim < inicio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "fim anterior ao início")
    cfg = PlannerConfig()
    dias: list[RotaDia] = []
    d = inicio
    while d <= fim:
        if d.weekday() != 6:
            dias.append(_carregar_ou_gerar_rota(session, pid, d, cfg, persistir=False))
        d += timedelta(days=1)
    return RotaPeriodo(profissional_id=pid, inicio=inicio, fim=fim, dias=dias)


@router.post(
    "/recalcular",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.GESTOR_UNIDADE, UserRole.GESTOR_AP, UserRole.ACS))],
)
def planner_recalcular(
    payload: RecalcularRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Recalcula e persiste a rota para [inicio, fim] do profissional informado.

    ACS só pode recalcular o próprio planner; gestores/admin para qualquer um.
    """
    pid = _resolver_profissional_id(user, payload.profissional_id)
    cfg = PlannerConfig(
        w_risco=payload.pesos.get("risco", 0.5) if payload.pesos else 0.5,
        w_proximidade=payload.pesos.get("proximidade", 0.3) if payload.pesos else 0.3,
        w_recencia=payload.pesos.get("recencia", 0.2) if payload.pesos else 0.2,
        n_max_visitas_dia=payload.n_max_visitas_dia or 12,
    )
    resultados = gerar_rota_periodo(session, pid, payload.inicio, payload.fim, cfg)
    for r in resultados:
        persistir_rota(session, r)
    log.info(
        "planner.recalculado",
        profissional_id=pid,
        inicio=str(payload.inicio),
        fim=str(payload.fim),
        dias=len(resultados),
    )
    return {"dias_gerados": len(resultados)}

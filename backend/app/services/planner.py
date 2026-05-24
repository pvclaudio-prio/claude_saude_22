"""Planner + roteirizador para o ACS.

Pontuação combinada (média ponderada, explicável):

    score_planner = w_risco      · s_risco
                  + w_proximidade · s_proximidade
                  + w_recencia    · s_recencia

Componentes (cada um normalizado em [0, 1]):

* **s_risco**       — score de risco do paciente / 100 (capado em 1.0).
* **s_proximidade** — 1 / (1 + dist_km/2). Aproxima 1 quando bem próximo,
                      decai suavemente. Permite que pacientes longe ainda
                      entrem na rota se o risco compensar.
* **s_recencia**    — min(1, dias_sem_visita / 365). Sem visita registrada
                      conta como 365 dias (máximo).

Pesos default: ``w_risco=0.5``, ``w_proximidade=0.3``, ``w_recencia=0.2``.
Soma = 1.0. Configurável em ``PlannerConfig``.

Algoritmo:

1. Pega todos os pacientes do escopo do profissional (equipe + visitados).
2. Calcula `score_planner` para cada um.
3. Seleciona os top-K (K = n_max_visitas) com maior `score_planner`.
4. Ordena espacialmente via nearest-neighbor a partir da sede da equipe
   — minimiza o deslocamento total mantendo a prioridade clínica.

Tudo explicável: cada paciente carrega ``componentes`` (s_risco, s_prox,
s_rec) + razão textual. Nada é inventado — só sai algo se houver dado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.db.models import (
    Equipe,
    Paciente,
    Profissional,
    RotaPlanejada,
    Visita,
)

log = get_logger("services.planner")


@dataclass(frozen=True)
class PlannerConfig:
    """Pesos e parâmetros do planner."""

    w_risco: float = 0.5
    w_proximidade: float = 0.3
    w_recencia: float = 0.2

    n_max_visitas_dia: int = 12
    # Caminhada do ACS no bairro — visitamos pacientes a até esse raio
    raio_max_km: float = 8.0

    # Cap superior do score de risco para normalização
    score_risco_cap: float = 100.0
    # Recência máxima considerada (em dias). Sem visita conta como esse valor.
    recencia_max_dias: int = 365


_CFG = PlannerConfig()


# ---------------------------------------------------------------------------
# Util — distância em km (haversine)
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos lat/lon (haversine)."""
    r_terra = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r_terra * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Componentes
# ---------------------------------------------------------------------------


@dataclass
class ComponentesScore:
    """Decomposição do score combinado para explicabilidade."""

    s_risco: float
    s_proximidade: float
    s_recencia: float
    distancia_km: float
    dias_sem_visita: int | None

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "s_risco": round(self.s_risco, 3),
            "s_proximidade": round(self.s_proximidade, 3),
            "s_recencia": round(self.s_recencia, 3),
            "distancia_km": round(self.distancia_km, 2),
            "dias_sem_visita": self.dias_sem_visita,
        }


@dataclass
class CandidatoVisita:
    """Paciente avaliado para entrar na rota — guarda score e motivos."""

    paciente_id: int
    nome_display: str
    lat: float
    lon: float
    score_combinado: float
    componentes: ComponentesScore
    motivos: list[str]


@dataclass
class RotaResultado:
    """Resultado da geração de rota — lista ordenada espacialmente."""

    profissional_id: int
    data: date
    paciente_ids: list[int]
    motivos: list[dict]
    componentes: list[dict]
    distancia_total_km: float


def _build_motivos(
    fatores_risco: Iterable[dict],
    componentes: ComponentesScore,
) -> list[str]:
    """Constrói lista de motivos textuais — primeiro fatores de risco,
    depois nota sobre distância e recência. Nada é inventado."""
    motivos: list[str] = []
    for f in fatores_risco:
        desc = f.get("descricao") if isinstance(f, dict) else None
        if desc:
            motivos.append(desc)
    if componentes.distancia_km > 0:
        motivos.append(f"A {componentes.distancia_km:.1f} km da sede da equipe.")
    if componentes.dias_sem_visita is None:
        motivos.append("Sem visita registrada anteriormente.")
    elif componentes.dias_sem_visita > 30:
        motivos.append(f"Última visita há {componentes.dias_sem_visita} dias.")
    return motivos


# ---------------------------------------------------------------------------
# Geração da rota
# ---------------------------------------------------------------------------


def _carregar_fatores_risco(
    session: Session, paciente_ids: list[int]
) -> dict[int, list[dict]]:
    """Carrega o último snapshot de RiscoPaciente.fatores por paciente."""
    from app.db.models import RiscoPaciente

    if not paciente_ids:
        return {}
    rows = session.exec(
        select(RiscoPaciente.paciente_id, RiscoPaciente.fatores, RiscoPaciente.atualizado_em)
        .where(RiscoPaciente.paciente_id.in_(paciente_ids))  # type: ignore[attr-defined]
        .order_by(RiscoPaciente.atualizado_em.desc())  # type: ignore[attr-defined]
    ).all()
    fatores_por_paciente: dict[int, list[dict]] = {}
    for pid, fatores, _ts in rows:
        if pid not in fatores_por_paciente:
            fatores_por_paciente[pid] = list(fatores or [])
    return fatores_por_paciente


def gerar_rota_dia(
    session: Session,
    profissional_id: int,
    data: date | None = None,
    cfg: PlannerConfig = _CFG,
    excluir_pacientes: set[int] | None = None,
) -> RotaResultado:
    """Gera a rota recomendada para um profissional num dia.

    Mesmo que ``data`` esteja no futuro, o planner usa o estado *atual* dos
    pacientes (score, última visita) para recomendar quem visitar. A data é
    só rótulo / persistência.
    """
    hoje = date.today()
    data = data or hoje

    prof = session.get(Profissional, profissional_id)
    if prof is None:
        raise ValueError(f"Profissional {profissional_id} não encontrado.")

    # Sede da equipe — referência para proximidade e início da rota
    equipe = session.get(Equipe, prof.equipe_id) if prof.equipe_id else None
    sede_lat = equipe.sede_lat if equipe else None
    sede_lon = equipe.sede_lon if equipe else None

    # Candidatos — pacientes da equipe + pacientes que ele já visitou
    candidatos = _candidatos_para_profissional(session, prof)
    if not candidatos:
        log.info("planner.sem_candidatos", profissional_id=profissional_id, data=str(data))
        return RotaResultado(profissional_id, data, [], [], [], 0.0)

    # Mapa: paciente_id -> última visita
    ult_visita = _ultima_visita_por_paciente(session, [p.id for p in candidatos if p.id])

    # Fatores de risco já calculados (precisa de /pacientes/recalcular-risco
    # ter sido rodado pelo menos uma vez)
    fatores_map = _carregar_fatores_risco(session, [p.id for p in candidatos if p.id])

    avaliados: list[CandidatoVisita] = []
    excluir = excluir_pacientes or set()
    for p in candidatos:
        if p.id is None:
            continue
        if p.id in excluir:
            continue
        if p.coordenada_outlier:
            # Não roteamos para pacientes com coordenada inválida
            continue

        dist = (
            haversine_km(sede_lat, sede_lon, p.endereco_latitude, p.endereco_longitude)
            if sede_lat is not None and sede_lon is not None
            else 0.0
        )
        if dist > cfg.raio_max_km:
            continue

        s_risco = min(1.0, (p.score_atual or 0.0) / cfg.score_risco_cap)
        s_prox = 1.0 / (1.0 + dist / 2.0)
        uv = ult_visita.get(p.id)
        if uv is None:
            dias = None
            s_rec = 1.0  # sem visita anterior → recência máxima
        else:
            dias = (hoje - uv).days
            s_rec = min(1.0, max(0.0, dias / cfg.recencia_max_dias))

        score_comb = (
            cfg.w_risco * s_risco
            + cfg.w_proximidade * s_prox
            + cfg.w_recencia * s_rec
        )

        componentes = ComponentesScore(s_risco, s_prox, s_rec, dist, dias)
        motivos = _build_motivos(fatores_map.get(p.id, []), componentes)

        avaliados.append(
            CandidatoVisita(
                paciente_id=p.id,
                nome_display=p.nome_display,
                lat=p.endereco_latitude,
                lon=p.endereco_longitude,
                score_combinado=score_comb,
                componentes=componentes,
                motivos=motivos,
            )
        )

    # Top-K por score
    avaliados.sort(key=lambda c: c.score_combinado, reverse=True)
    top = avaliados[: cfg.n_max_visitas_dia]

    # Ordenação espacial — greedy nearest-neighbor desde a sede
    ordenados = _nearest_neighbor_path(top, sede_lat, sede_lon)

    # Distância total da rota
    dist_total = 0.0
    if sede_lat is not None and sede_lon is not None and ordenados:
        prev_lat, prev_lon = sede_lat, sede_lon
        for c in ordenados:
            dist_total += haversine_km(prev_lat, prev_lon, c.lat, c.lon)
            prev_lat, prev_lon = c.lat, c.lon

    motivos_out = [
        {
            "paciente_id": c.paciente_id,
            "nome_display": c.nome_display,
            "score_combinado": round(c.score_combinado, 3),
            "motivos": c.motivos,
        }
        for c in ordenados
    ]
    componentes_out = [
        {"paciente_id": c.paciente_id, **c.componentes.to_dict()} for c in ordenados
    ]

    return RotaResultado(
        profissional_id=profissional_id,
        data=data,
        paciente_ids=[c.paciente_id for c in ordenados],
        motivos=motivos_out,
        componentes=componentes_out,
        distancia_total_km=round(dist_total, 2),
    )


def gerar_rota_periodo(
    session: Session,
    profissional_id: int,
    inicio: date,
    fim: date,
    cfg: PlannerConfig = _CFG,
) -> list[RotaResultado]:
    """Gera rotas para cada dia de ``inicio`` a ``fim`` (inclusive), pulando
    domingos. Pacientes já roteirizados em um dia anterior são **excluídos
    do pool de candidatos** dos dias seguintes — evita repetição mas permite
    que cada dia tenha sua própria top-K com pacientes restantes."""
    if fim < inicio:
        raise ValueError("fim < inicio")
    resultados: list[RotaResultado] = []
    visitados_na_semana: set[int] = set()

    dia = inicio
    while dia <= fim:
        if dia.weekday() == 6:  # domingo
            dia += timedelta(days=1)
            continue

        r = gerar_rota_dia(
            session, profissional_id, dia, cfg,
            excluir_pacientes=visitados_na_semana,
        )
        visitados_na_semana.update(r.paciente_ids)
        resultados.append(r)
        dia += timedelta(days=1)
    return resultados


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------


def persistir_rota(session: Session, resultado: RotaResultado) -> RotaPlanejada:
    """Upsert: salva (ou substitui) a rota planejada para o (profissional, data)."""
    existente = session.exec(
        select(RotaPlanejada)
        .where(RotaPlanejada.profissional_id == resultado.profissional_id)
        .where(RotaPlanejada.data == resultado.data)
    ).first()
    if existente is not None:
        session.delete(existente)
        session.flush()
    rota = RotaPlanejada(
        profissional_id=resultado.profissional_id,
        data=resultado.data,
        paciente_ids=resultado.paciente_ids,
        motivos=resultado.motivos,
    )
    session.add(rota)
    session.commit()
    session.refresh(rota)
    return rota


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _candidatos_para_profissional(session: Session, prof: Profissional) -> list[Paciente]:
    """Pacientes da equipe modal + pacientes já visitados pelo profissional."""
    from sqlalchemy import or_

    conditions = []
    if prof.equipe_id is not None:
        conditions.append(Paciente.equipe_id == prof.equipe_id)
    if prof.id is not None:
        sub = select(Visita.paciente_id).where(Visita.profissional_id == prof.id)
        conditions.append(Paciente.id.in_(sub))  # type: ignore[attr-defined]
    if not conditions:
        return []
    q = select(Paciente).where(or_(*conditions))
    return list(session.exec(q).all())


def _ultima_visita_por_paciente(session: Session, paciente_ids: list[int]) -> dict[int, date]:
    if not paciente_ids:
        return {}
    rows = session.exec(
        select(Visita.paciente_id, func.max(Visita.data))
        .where(Visita.paciente_id.in_(paciente_ids))  # type: ignore[attr-defined]
        .group_by(Visita.paciente_id)
    ).all()
    return {pid: d for pid, d in rows}


def _nearest_neighbor_path(
    candidatos: list[CandidatoVisita],
    start_lat: float | None,
    start_lon: float | None,
) -> list[CandidatoVisita]:
    """Greedy nearest-neighbor TSP — a partir do ponto inicial (sede)."""
    if not candidatos or start_lat is None or start_lon is None:
        return candidatos
    restantes = candidatos[:]
    rota: list[CandidatoVisita] = []
    cur_lat, cur_lon = start_lat, start_lon
    while restantes:
        proximo = min(
            restantes,
            key=lambda c: haversine_km(cur_lat, cur_lon, c.lat, c.lon),
        )
        rota.append(proximo)
        restantes.remove(proximo)
        cur_lat, cur_lon = proximo.lat, proximo.lon
    return rota

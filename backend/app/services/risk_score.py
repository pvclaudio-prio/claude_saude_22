"""Score de risco explicável para priorização de visitas do ACS.

Soma ponderada de fatores observáveis. Cada fator gera uma string de
justificativa — a UI exibe a lista para o ACS entender por que aquele
paciente é prioritário. **Nunca inventamos motivo sem dado**.

Pesos e thresholds são parametrizáveis. Os defaults seguem o CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.db.models import (
    AlertaPaciente,
    EventoClinico,
    NivelRisco,
    Paciente,
    RegistroVisita,
    RiscoPaciente,
    TipoEventoClinico,
    Visita,
)

log = get_logger("services.risk_score")


# ---------------------------------------------------------------------------
# Configuração de pesos / thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreConfig:
    """Pesos do score (calibrados para o piloto)."""

    peso_vulnerabilidade: int = 25
    peso_gestacao: int = 20
    peso_idoso: int = 12  # faixa 66+
    peso_crianca: int = 10  # faixa 0-6
    peso_hipertensao: int = 6
    peso_diabetes: int = 6
    peso_urgencia_30d: int = 25
    peso_urgencia_90d: int = 12
    peso_agendamento_proximo: int = 8  # ≤ 14 dias
    peso_sem_visita_90d: int = 10
    peso_sem_visita_180d: int = 18
    peso_violencia_registrada: int = 30
    peso_necessidades_especiais: int = 8

    # Thresholds
    threshold_moderado: int = 20
    threshold_alto: int = 40
    threshold_critico: int = 60

    janela_urgencia_30d: int = 30
    janela_urgencia_90d: int = 90
    janela_agendamento: int = 14
    janela_sem_visita_alto: int = 180
    janela_sem_visita_medio: int = 90


_CFG = ScoreConfig()


def nivel_por_score(score: float, cfg: ScoreConfig = _CFG) -> NivelRisco:
    if score >= cfg.threshold_critico:
        return NivelRisco.CRITICO
    if score >= cfg.threshold_alto:
        return NivelRisco.ALTO
    if score >= cfg.threshold_moderado:
        return NivelRisco.MODERADO
    return NivelRisco.BAIXO


@dataclass
class Fator:
    """Item que contribuiu para o score (com justificativa amigável)."""

    chave: str
    peso: int
    descricao: str

    def to_dict(self) -> dict[str, str | int]:
        return {"chave": self.chave, "peso": self.peso, "descricao": self.descricao}


@dataclass
class ScoreResult:
    paciente_id: int
    score: float
    nivel: NivelRisco
    fatores: list[Fator] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cálculo individual
# ---------------------------------------------------------------------------


def calcular_score_paciente(
    paciente: Paciente,
    *,
    eventos_recentes: Iterable[EventoClinico],
    ultima_visita: date | None,
    registros: Iterable[RegistroVisita],
    alertas: Iterable[AlertaPaciente] | None = None,
    hoje: date | None = None,
    cfg: ScoreConfig = _CFG,
) -> ScoreResult:
    """Calcula o score do paciente a partir do contexto já carregado.

    Receber os agregados como argumento (em vez de buscar no banco) permite
    reusar o cálculo em batch sem queries N+1.
    """
    hoje = hoje or date.today()
    fatores: list[Fator] = []

    if paciente.situacao_vulnerabilidade:
        fatores.append(
            Fator(
                "vulnerabilidade",
                cfg.peso_vulnerabilidade,
                "Paciente em situação de vulnerabilidade social.",
            )
        )
    if paciente.gestacao:
        fatores.append(Fator("gestacao", cfg.peso_gestacao, "Paciente gestante."))
    if paciente.faixa_etaria == "66+":
        fatores.append(Fator("idoso", cfg.peso_idoso, "Paciente idoso (66+)."))
    if paciente.faixa_etaria == "0-6":
        fatores.append(Fator("crianca", cfg.peso_crianca, "Criança 0-6 anos."))
    if paciente.hipertenso:
        fatores.append(Fator("hipertensao", cfg.peso_hipertensao, "Hipertensão referida."))
    if paciente.diabetico:
        fatores.append(Fator("diabetes", cfg.peso_diabetes, "Diabetes referida."))

    # Eventos clínicos
    limite_30 = hoje - timedelta(days=cfg.janela_urgencia_30d)
    limite_90 = hoje - timedelta(days=cfg.janela_urgencia_90d)
    limite_agend = hoje + timedelta(days=cfg.janela_agendamento)

    teve_urg_30 = False
    teve_urg_90 = False
    teve_agend_proximo = False
    for e in eventos_recentes:
        d = e.data_referencia
        if e.tipo is TipoEventoClinico.URGENCIA:
            if d >= limite_30:
                teve_urg_30 = True
            elif d >= limite_90:
                teve_urg_90 = True
        elif e.tipo is TipoEventoClinico.AGENDAMENTO:
            if hoje <= d <= limite_agend:
                teve_agend_proximo = True

    if teve_urg_30:
        fatores.append(
            Fator(
                "urgencia_30d",
                cfg.peso_urgencia_30d,
                "Evento de urgência/emergência/internação nos últimos 30 dias.",
            )
        )
    elif teve_urg_90:
        fatores.append(
            Fator(
                "urgencia_90d",
                cfg.peso_urgencia_90d,
                "Evento de urgência/emergência/internação nos últimos 90 dias.",
            )
        )
    if teve_agend_proximo:
        fatores.append(
            Fator(
                "agendamento_proximo",
                cfg.peso_agendamento_proximo,
                f"Agendamento nos próximos {cfg.janela_agendamento} dias.",
            )
        )

    # Lacuna de visita
    if ultima_visita is None:
        fatores.append(
            Fator(
                "sem_visita_registrada",
                cfg.peso_sem_visita_180d,
                "Sem visita registrada nos dados.",
            )
        )
    else:
        delta_dias = (hoje - ultima_visita).days
        if delta_dias > cfg.janela_sem_visita_alto:
            fatores.append(
                Fator(
                    "sem_visita_180d",
                    cfg.peso_sem_visita_180d,
                    f"Sem visita há {delta_dias} dias (>{cfg.janela_sem_visita_alto}).",
                )
            )
        elif delta_dias > cfg.janela_sem_visita_medio:
            fatores.append(
                Fator(
                    "sem_visita_90d",
                    cfg.peso_sem_visita_90d,
                    f"Sem visita há {delta_dias} dias (>{cfg.janela_sem_visita_medio}).",
                )
            )

    # Registros estruturados — sinais críticos
    for r in registros:
        if r.violencia and r.violencia.get("suspeita"):
            fatores.append(
                Fator(
                    "violencia_suspeita",
                    cfg.peso_violencia_registrada,
                    "Suspeita de violência registrada em visita anterior.",
                )
            )
            break  # peso aplicado uma vez
    for r in registros:
        if r.necessidades_especiais:
            fatores.append(
                Fator(
                    "necessidades_especiais",
                    cfg.peso_necessidades_especiais,
                    "Necessidades especiais registradas.",
                )
            )
            break

    # Alertas manuais (futuro) — não somam aqui no MVP

    score = float(sum(f.peso for f in fatores))
    nivel = nivel_por_score(score, cfg)
    return ScoreResult(paciente_id=paciente.id or -1, score=score, nivel=nivel, fatores=fatores)


# ---------------------------------------------------------------------------
# Batch — recalcula todos os pacientes
# ---------------------------------------------------------------------------


def recalcular_todos(session: Session, *, hoje: date | None = None) -> int:
    """Recalcula score para todos os pacientes e atualiza `Paciente.score_atual`
    + `Paciente.nivel_risco` + insere snapshot em `RiscoPaciente`.

    Retorna o número de pacientes processados.
    """
    hoje = hoje or date.today()

    # Carrega tudo em DataFrame-like: usamos um único pass por tabela.
    pacientes = session.exec(select(Paciente)).all()

    # Última visita por paciente
    ult_visita_rows = session.exec(
        select(Visita.paciente_id, func.max(Visita.data)).group_by(Visita.paciente_id)
    ).all()
    ult_visita_map: dict[int, date] = {pid: d for pid, d in ult_visita_rows}

    # Eventos recentes (últimos 6 meses) por paciente
    limite = hoje - timedelta(days=200)
    eventos = session.exec(
        select(EventoClinico).where(EventoClinico.data_referencia >= limite)
    ).all()
    eventos_por_paciente: dict[int, list[EventoClinico]] = {}
    for e in eventos:
        eventos_por_paciente.setdefault(e.paciente_id, []).append(e)

    # Agendamentos futuros (até 30 dias)
    futuros = session.exec(
        select(EventoClinico)
        .where(EventoClinico.tipo == TipoEventoClinico.AGENDAMENTO)
        .where(EventoClinico.data_referencia >= hoje)
        .where(EventoClinico.data_referencia <= hoje + timedelta(days=30))
    ).all()
    for e in futuros:
        eventos_por_paciente.setdefault(e.paciente_id, []).append(e)

    # Registros estruturados (todos)
    registros = session.exec(select(RegistroVisita)).all()
    registros_por_paciente: dict[int, list[RegistroVisita]] = {}
    for r in registros:
        registros_por_paciente.setdefault(r.paciente_id, []).append(r)

    processados = 0
    for p in pacientes:
        assert p.id is not None
        result = calcular_score_paciente(
            p,
            eventos_recentes=eventos_por_paciente.get(p.id, []),
            ultima_visita=ult_visita_map.get(p.id),
            registros=registros_por_paciente.get(p.id, []),
            hoje=hoje,
        )
        p.score_atual = result.score
        p.nivel_risco = result.nivel
        p.ultima_visita_em = ult_visita_map.get(p.id)
        snap = RiscoPaciente(
            paciente_id=p.id,
            score=result.score,
            nivel=result.nivel,
            fatores=[f.to_dict() for f in result.fatores],
        )
        session.add(snap)
        processados += 1

    session.commit()
    log.info("risk_score.recalculado", n=processados)
    return processados

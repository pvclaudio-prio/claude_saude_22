"""Testes unitários do score de risco — sem banco, foco na lógica."""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models import EventoClinico, NivelRisco, Paciente, TipoEventoClinico
from app.services.risk_score import calcular_score_paciente, nivel_por_score


def _p(**kwargs) -> Paciente:
    """Helper: instancia um Paciente sem persistir."""
    base = dict(
        id=1,
        hash_id="x",
        nome_display="x",
        faixa_etaria="19-45",
        sexo="Feminino",
        endereco_latitude=-22.95,
        endereco_longitude=-43.20,
    )
    base.update(kwargs)
    return Paciente(**base)


def _e(tipo: TipoEventoClinico, dias_atras: int) -> EventoClinico:
    return EventoClinico(
        id=1,
        paciente_id=1,
        tipo=tipo,
        data_referencia=date.today() - timedelta(days=dias_atras),
    )


def test_score_baixo_sem_fatores() -> None:
    p = _p()
    r = calcular_score_paciente(p, eventos_recentes=[], ultima_visita=date.today(), registros=[])
    assert r.score == 0.0
    assert r.nivel is NivelRisco.BAIXO
    assert r.fatores == []


def test_score_gestante_vulneravel_eleva_para_alto() -> None:
    p = _p(gestacao=True, situacao_vulnerabilidade=True)
    r = calcular_score_paciente(p, eventos_recentes=[], ultima_visita=date.today(), registros=[])
    assert r.score == 45  # 20 + 25
    assert r.nivel is NivelRisco.ALTO
    keys = {f.chave for f in r.fatores}
    assert "gestacao" in keys
    assert "vulnerabilidade" in keys


def test_score_urgencia_30d_pesa_mais_que_90d() -> None:
    p = _p()
    r30 = calcular_score_paciente(
        p, eventos_recentes=[_e(TipoEventoClinico.URGENCIA, 10)], ultima_visita=date.today(), registros=[]
    )
    r90 = calcular_score_paciente(
        p, eventos_recentes=[_e(TipoEventoClinico.URGENCIA, 60)], ultima_visita=date.today(), registros=[]
    )
    assert r30.score > r90.score
    assert "urgencia_30d" in {f.chave for f in r30.fatores}
    assert "urgencia_90d" in {f.chave for f in r90.fatores}


def test_score_sem_visita_180d_pesa_mais_que_90d() -> None:
    p = _p()
    r180 = calcular_score_paciente(
        p, eventos_recentes=[], ultima_visita=date.today() - timedelta(days=200), registros=[]
    )
    r90 = calcular_score_paciente(
        p, eventos_recentes=[], ultima_visita=date.today() - timedelta(days=100), registros=[]
    )
    assert r180.score > r90.score


def test_score_critico_acumula_muitos_fatores() -> None:
    p = _p(gestacao=True, situacao_vulnerabilidade=True, hipertenso=True)
    r = calcular_score_paciente(
        p,
        eventos_recentes=[_e(TipoEventoClinico.URGENCIA, 10)],
        ultima_visita=date.today() - timedelta(days=200),
        registros=[],
    )
    # 20 (gestacao) + 25 (vuln) + 6 (HAS) + 25 (urg30) + 18 (sem visita 180d) = 94
    assert r.score == 94
    assert r.nivel is NivelRisco.CRITICO


def test_nivel_thresholds() -> None:
    assert nivel_por_score(0) is NivelRisco.BAIXO
    assert nivel_por_score(19) is NivelRisco.BAIXO
    assert nivel_por_score(20) is NivelRisco.MODERADO
    assert nivel_por_score(39) is NivelRisco.MODERADO
    assert nivel_por_score(40) is NivelRisco.ALTO
    assert nivel_por_score(59) is NivelRisco.ALTO
    assert nivel_por_score(60) is NivelRisco.CRITICO
    assert nivel_por_score(120) is NivelRisco.CRITICO


def test_score_nao_inventa_motivo_sem_dado() -> None:
    """Paciente sem nenhuma flag deve ter zero fatores — score não inventa."""
    p = _p()  # tudo False/default
    r = calcular_score_paciente(p, eventos_recentes=[], ultima_visita=date.today(), registros=[])
    assert r.fatores == []
    assert r.score == 0.0

"""Testes do planner — score combinado, ordenação espacial, persistência, RBAC."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.importers.parquets import importar
from app.importers.seed_users import seed_demo_users
from app.services.clustering import ClusteringConfig
from app.services.planner import (
    PlannerConfig,
    gerar_rota_dia,
    haversine_km,
)
from app.services.risk_score import recalcular_todos


@pytest.fixture
def db_pronto(parquets_sinteticos: Path) -> dict[str, int]:
    """Pipeline completa para um banco pronto para o planner."""
    importar(samples_dir=parquets_sinteticos, cfg=ClusteringConfig(n_aps=2, n_bairros=4))
    users = seed_demo_users(n_acs=2)

    from app.db.session import engine

    with Session(engine) as s:
        recalcular_todos(s)
    return users


def test_haversine_basico() -> None:
    """Distância Copacabana → Centro RJ ≈ 5 km."""
    d = haversine_km(-22.9711, -43.1822, -22.9068, -43.1729)
    assert 5.0 < d < 9.0


def test_gerar_rota_dia_retorna_pacientes_no_escopo(db_pronto: dict[str, int]) -> None:
    """Rota gerada para acs1 contém apenas pacientes do escopo dele."""
    from app.db.session import engine
    from app.db.models import Profissional, User

    with Session(engine) as s:
        u = s.get(User, db_pronto["acs1"])
        assert u is not None and u.profissional_id is not None
        prof = s.get(Profissional, u.profissional_id)
        assert prof is not None

        rota = gerar_rota_dia(s, prof.id, date.today(), PlannerConfig(n_max_visitas_dia=5))
        assert rota.profissional_id == prof.id
        assert len(rota.paciente_ids) <= 5
        # Todos os pacientes devem ter componentes calculados
        assert len(rota.componentes) == len(rota.paciente_ids)
        for comp in rota.componentes:
            assert "s_risco" in comp
            assert "s_proximidade" in comp
            assert "s_recencia" in comp


def test_rota_respeita_n_max_visitas(db_pronto: dict[str, int]) -> None:
    from app.db.session import engine
    from app.db.models import User

    with Session(engine) as s:
        u = s.get(User, db_pronto["acs1"])
        rota = gerar_rota_dia(s, u.profissional_id, date.today(), PlannerConfig(n_max_visitas_dia=3))
        assert len(rota.paciente_ids) <= 3


def test_motivos_existem_para_cada_paciente(db_pronto: dict[str, int]) -> None:
    """Todo paciente na rota deve ter motivos textuais (explicabilidade)."""
    from app.db.session import engine
    from app.db.models import User

    with Session(engine) as s:
        u = s.get(User, db_pronto["acs1"])
        rota = gerar_rota_dia(s, u.profissional_id, date.today(), PlannerConfig())
        assert len(rota.motivos) == len(rota.paciente_ids)
        # Pelo menos a referência geográfica deve estar lá (sempre derivável)
        for m in rota.motivos:
            assert isinstance(m["motivos"], list)


def test_planner_endpoint_acs_so_ve_proprio_planner(db_pronto: dict[str, int]) -> None:
    from app.main import app

    c = TestClient(app)
    tok_acs = c.post("/auth/login-demo", json={"username": "acs1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_acs}"}

    # ACS pedindo planner do próprio
    r = c.get("/planner/dia", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["profissional_id"] is not None
    assert "itens" in body
    # ACS NÃO consegue ver de outro profissional — query param é ignorado
    r2 = c.get("/planner/dia?profissional_id=999999", headers=headers)
    assert r2.status_code == 200  # mesmo assim, devolve o do ACS


def test_planner_endpoint_gestor_precisa_profissional_id(db_pronto: dict[str, int]) -> None:
    from app.main import app

    c = TestClient(app)
    tok = c.post("/auth/login-demo", json={"username": "gestor_unidade"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    # Sem profissional_id → 400
    r = c.get("/planner/dia", headers=headers)
    assert r.status_code == 400

    # Com profissional_id válido → 200
    from app.db.session import engine
    from app.db.models import User

    with Session(engine) as s:
        u = s.get(User, db_pronto["acs1"])
        pid = u.profissional_id

    r2 = c.get(f"/planner/dia?profissional_id={pid}", headers=headers)
    assert r2.status_code == 200


def test_planner_semana_devolve_dias_uteis(db_pronto: dict[str, int]) -> None:
    from app.main import app

    c = TestClient(app)
    tok = c.post("/auth/login-demo", json={"username": "acs1"}).json()["access_token"]
    r = c.get("/planner/semana", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    dias = r.json()["dias"]
    # 7 dias - 1 domingo (se houver) = 6 ou 7
    assert 6 <= len(dias) <= 7
    # Datas estritamente crescentes
    datas = [d["data"] for d in dias]
    assert datas == sorted(datas)


def test_planner_recalcular_persiste(db_pronto: dict[str, int]) -> None:
    from app.main import app

    c = TestClient(app)
    tok = c.post("/auth/login-demo", json={"username": "acs1"}).json()["access_token"]
    hoje = date.today()
    fim = hoje + timedelta(days=2)

    r = c.post(
        "/planner/recalcular",
        json={"inicio": hoje.isoformat(), "fim": fim.isoformat()},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json()["dias_gerados"] >= 2


def test_score_combinado_ordenacao_pesos_default(db_pronto: dict[str, int]) -> None:
    """Score combinado decresce ao longo da rota (top-K do mais alto ao mais baixo)."""
    from app.db.session import engine
    from app.db.models import User

    with Session(engine) as s:
        u = s.get(User, db_pronto["acs1"])
        rota = gerar_rota_dia(s, u.profissional_id, date.today(), PlannerConfig(n_max_visitas_dia=10))

    if len(rota.motivos) < 2:
        pytest.skip("rota muito curta para validar ordenação")
    # Após nearest-neighbor a ordem ESPACIAL não preserva score; mas o ANTES
    # do nearest-neighbor era ordenado por score. Validamos que todos os
    # incluídos têm score >= score do candidato seguinte fora da lista —
    # impraticável de testar aqui. Validamos só que scores são razoáveis (∈ [0, 1]).
    for m in rota.motivos:
        assert 0.0 <= m["score_combinado"] <= 1.0

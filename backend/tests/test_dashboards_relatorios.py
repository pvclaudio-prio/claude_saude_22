"""Testes dos endpoints de dashboards e relatórios."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.importers.parquets import importar
from app.importers.seed_users import seed_demo_users
from app.services.clustering import ClusteringConfig
from app.services.risk_score import recalcular_todos


@pytest.fixture
def client(parquets_sinteticos: Path) -> TestClient:
    importar(samples_dir=parquets_sinteticos, cfg=ClusteringConfig(n_aps=2, n_bairros=4))
    seed_demo_users(n_acs=2)
    from app.db.session import engine
    from sqlmodel import Session

    with Session(engine) as s:
        recalcular_todos(s)
    from app.main import app

    return TestClient(app)


def _login(client: TestClient, username: str) -> dict[str, str]:
    tok = client.post("/auth/login-demo", json={"username": username}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_kpis_devolve_estrutura_completa(client: TestClient) -> None:
    r = client.get("/dashboards/kpis", headers=_login(client, "admin"))
    assert r.status_code == 200
    body = r.json()
    for k in [
        "pacientes_total", "pacientes_criticos", "pacientes_alto_risco",
        "gestantes", "hipertensos", "diabeticos", "sem_visita_90d",
        "visitas_ultimo_mes", "eventos_urgencia_30d", "score_medio", "escopo",
    ]:
        assert k in body
    assert body["pacientes_total"] >= 1


def test_kpis_acs_subset(client: TestClient) -> None:
    r_admin = client.get("/dashboards/kpis", headers=_login(client, "admin")).json()
    r_acs = client.get("/dashboards/kpis", headers=_login(client, "acs1")).json()
    # ACS deve ter <= total do admin
    assert r_acs["pacientes_total"] <= r_admin["pacientes_total"]


def test_mapa_devolve_pontos_e_sedes(client: TestClient) -> None:
    r = client.get("/dashboards/mapa?limit=50", headers=_login(client, "admin"))
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["pacientes"], list)
    assert isinstance(body["sedes_equipes"], list)
    # Cada ponto tem lat/lon
    for p in body["pacientes"]:
        assert "lat" in p and "lon" in p


def test_mapa_nao_traz_outliers(client: TestClient) -> None:
    r = client.get("/dashboards/mapa?limit=200", headers=_login(client, "admin")).json()
    # Fixture tem 1 outlier (P_OUT) — não deve aparecer
    hashes = [p["nome_display"] for p in r["pacientes"]]
    assert not any("P_OUT" in h for h in hashes)


def test_heatmap_vulnerabilidade(client: TestClient) -> None:
    r = client.get("/dashboards/heatmap?tipo=vulnerabilidade", headers=_login(client, "admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["tipo"] == "vulnerabilidade"
    assert isinstance(body["pontos"], list)


def test_heatmap_tipo_invalido_422(client: TestClient) -> None:
    r = client.get("/dashboards/heatmap?tipo=zzz", headers=_login(client, "admin"))
    assert r.status_code == 422


def test_ranking_pacientes_ordenado(client: TestClient) -> None:
    r = client.get(
        "/dashboards/ranking-pacientes?limit=10", headers=_login(client, "admin")
    ).json()
    items = r["items"]
    scores = [i["score"] for i in items]
    assert scores == sorted(scores, reverse=True)


def test_relatorio_acs_dia(client: TestClient) -> None:
    r = client.get("/relatorios/acs-dia", headers=_login(client, "acs1"))
    assert r.status_code == 200
    body = r.json()
    assert "rota" in body
    assert "totais" in body


def test_relatorio_gestor_periodo(client: TestClient) -> None:
    hoje = date.today()
    r = client.get(
        f"/relatorios/gestor-periodo?inicio={hoje - timedelta(days=30)}&fim={hoje}",
        headers=_login(client, "gestor_unidade"),
    )
    assert r.status_code == 200
    body = r.json()
    assert "totais" in body
    assert "riscos_por_equipe" in body
    assert "pacientes_criticos" in body


def test_relatorio_gestor_periodo_negado_para_acs(client: TestClient) -> None:
    hoje = date.today()
    r = client.get(
        f"/relatorios/gestor-periodo?inicio={hoje - timedelta(days=7)}&fim={hoje}",
        headers=_login(client, "acs1"),
    )
    assert r.status_code == 403

"""Testes de RegistroVisita — schemas de ficha + endpoints + auditoria + escopo."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, select

from app.db.models import Auditoria, FichaTipo, Paciente, Visita
from app.importers.parquets import importar
from app.importers.seed_users import seed_demo_users
from app.schemas.fichas import (
    FichaCronico,
    FichaGestante,
    FichaPrimeiraInfancia,
    FichaTB,
    validar_respostas_ficha,
)
from app.services.clustering import ClusteringConfig
from app.services.registros import sugerir_ficha


# ---------------------------------------------------------------------------
# Schemas de ficha — validação Pydantic
# ---------------------------------------------------------------------------


def test_ficha_gestante_aceita_pressao_arterial_valida() -> None:
    f = FichaGestante(
        semana_gestacional=20,
        mediu_pressao="sim",
        pressoes_registradas=[{"data": "2026-05-24", "sistolica": 120, "diastolica": 80}],
    )
    assert len(f.pressoes_registradas) == 1
    assert f.pressoes_registradas[0].sistolica == 120


def test_ficha_gestante_rejeita_pressao_fora_de_faixa() -> None:
    with pytest.raises(ValidationError):
        FichaGestante(
            pressoes_registradas=[{"data": "2026-05-24", "sistolica": 999, "diastolica": 50}],
        )


def test_ficha_primeira_infancia_idade_valida() -> None:
    f = FichaPrimeiraInfancia(idade_meses=3, primeira_consulta_em_7_dias="sim")
    assert f.idade_meses == 3
    with pytest.raises(ValidationError):
        FichaPrimeiraInfancia(idade_meses=120)  # > 6 anos


def test_ficha_cronico_enum_estilo_vida() -> None:
    f = FichaCronico(mudanca_estilo_de_vida="cessando_tabagismo")
    assert f.mudanca_estilo_de_vida == "cessando_tabagismo"
    with pytest.raises(ValidationError):
        FichaCronico(mudanca_estilo_de_vida="malhar_mais")  # type: ignore[arg-type]


def test_ficha_tb_contatos_negativos_rejeitados() -> None:
    with pytest.raises(ValidationError):
        FichaTB(contatos_total=-1)


def test_validar_respostas_ficha_polimorfico() -> None:
    """Mesma função despacha por ficha_tipo."""
    out_gest = validar_respostas_ficha(FichaTipo.GESTANTE, {"semana_gestacional": 12})
    assert out_gest["semana_gestacional"] == 12

    out_cron = validar_respostas_ficha(FichaTipo.CRONICO, {"esqueceu_dose_2sem": "nao"})
    assert out_cron["esqueceu_dose_2sem"] == "nao"


# ---------------------------------------------------------------------------
# Sugestor de ficha
# ---------------------------------------------------------------------------


def _make_pac(**kw) -> Paciente:
    base = dict(
        id=1, hash_id="x", nome_display="x",
        faixa_etaria="19-45", sexo="Feminino",
        endereco_latitude=-22.95, endereco_longitude=-43.20,
    )
    base.update(kw)
    return Paciente(**base)


def test_sugestor_ficha_gestante_tem_precedencia() -> None:
    p = _make_pac(gestacao=True, hipertenso=True)
    assert sugerir_ficha(p) is FichaTipo.GESTANTE


def test_sugestor_ficha_crianca_06() -> None:
    p = _make_pac(faixa_etaria="0-6")
    assert sugerir_ficha(p) is FichaTipo.PRIMEIRA_INFANCIA


def test_sugestor_ficha_cronico_idoso_has_dm() -> None:
    assert sugerir_ficha(_make_pac(hipertenso=True)) is FichaTipo.CRONICO
    assert sugerir_ficha(_make_pac(diabetico=True)) is FichaTipo.CRONICO
    assert sugerir_ficha(_make_pac(faixa_etaria="66+")) is FichaTipo.CRONICO


def test_sugestor_ficha_livre_default() -> None:
    assert sugerir_ficha(_make_pac()) is FichaTipo.LIVRE


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def client(parquets_sinteticos: Path) -> TestClient:
    importar(samples_dir=parquets_sinteticos, cfg=ClusteringConfig(n_aps=2, n_bairros=4))
    seed_demo_users(n_acs=2)
    from app.main import app

    return TestClient(app)


def _login(client: TestClient, username: str) -> str:
    r = client.post("/auth/login-demo", json={"username": username})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def test_acs_cria_registro_e_aparece_na_timeline(client: TestClient) -> None:
    tok = _login(client, "acs1")
    # pega um paciente no escopo do ACS
    pacs = client.get("/pacientes?limit=2000", headers=_auth(tok)).json()
    assert pacs, "ACS sem pacientes no escopo"
    pid = pacs[0]["id"]

    payload = {
        "paciente_id": pid,
        "ficha_tipo": "livre",
        "respostas": {"observacoes": "Visita de rotina."},
        "resumo": "Tudo bem. Paciente estável.",
        "sinais_risco": [],
        "status": "visitado",
    }
    r = client.post("/registros-visita", json=payload, headers=_auth(tok))
    assert r.status_code == 200, r.text
    reg_id = r.json()["id"]

    # Aparece na timeline
    tl = client.get(f"/pacientes/{pid}/timeline", headers=_auth(tok)).json()
    tipos = {i["tipo"] for i in tl["itens"]}
    assert "registro_visita" in tipos

    # Reaparece em /by-paciente
    lista = client.get(f"/registros-visita/by-paciente/{pid}", headers=_auth(tok)).json()
    assert any(r["id"] == reg_id for r in lista)


def test_gestor_nao_pode_criar_registro(client: TestClient) -> None:
    tok = _login(client, "gestor_unidade")
    pacs = client.get("/pacientes?limit=5", headers=_auth(tok)).json()
    assert pacs
    payload = {"paciente_id": pacs[0]["id"], "ficha_tipo": "livre"}
    r = client.post("/registros-visita", json=payload, headers=_auth(tok))
    assert r.status_code == 403


def test_registro_com_ficha_gestante_valida_pa(client: TestClient) -> None:
    tok = _login(client, "acs1")
    pacs = client.get("/pacientes?limit=2000", headers=_auth(tok)).json()
    pid = pacs[0]["id"]

    # PA com sistólica absurda → erro de validação
    bad = {
        "paciente_id": pid,
        "ficha_tipo": "gestante",
        "respostas": {
            "semana_gestacional": 20,
            "pressoes_registradas": [{"data": "2026-05-24", "sistolica": 999, "diastolica": 80}],
        },
    }
    r = client.post("/registros-visita", json=bad, headers=_auth(tok))
    assert r.status_code in (400, 422)


def test_sugerir_ficha_endpoint(client: TestClient) -> None:
    tok = _login(client, "acs1")
    pacs = client.get("/pacientes?limit=2000", headers=_auth(tok)).json()
    # acha qualquer paciente
    pid = pacs[0]["id"]
    r = client.get(f"/registros-visita/sugerir-ficha/{pid}", headers=_auth(tok))
    assert r.status_code == 200
    assert r.json()["ficha_tipo"] in {"livre", "ficha_a", "gestante", "primeira_infancia", "tb", "cronico"}


def test_paciente_detalhe_inclui_ficha_sugerida(client: TestClient) -> None:
    tok = _login(client, "acs1")
    pacs = client.get("/pacientes?limit=10", headers=_auth(tok)).json()
    pid = pacs[0]["id"]
    r = client.get(f"/pacientes/{pid}", headers=_auth(tok))
    assert r.status_code == 200
    body = r.json()
    assert "ficha_sugerida" in body
    assert body["ficha_sugerida"]


def test_criacao_audita(client: TestClient, db_session: Session) -> None:
    tok = _login(client, "acs1")
    pacs = client.get("/pacientes?limit=5", headers=_auth(tok)).json()
    pid = pacs[0]["id"]
    payload = {"paciente_id": pid, "ficha_tipo": "livre", "respostas": {"observacoes": "ok"}}
    r = client.post("/registros-visita", json=payload, headers=_auth(tok))
    assert r.status_code == 200

    with db_session as s:
        rows = s.exec(
            select(Auditoria)
            .where(Auditoria.entity_type == "registro_visita")
            .where(Auditoria.action == "criar")
        ).all()
        assert len(rows) >= 1
        # nunca expor payload bruto — só hash
        assert all(a.payload_hash and len(a.payload_hash) == 64 for a in rows)


def test_visita_criada_associada_ao_registro(client: TestClient, db_session: Session) -> None:
    tok = _login(client, "acs1")
    pacs = client.get("/pacientes?limit=5", headers=_auth(tok)).json()
    pid = pacs[0]["id"]
    n_visitas_antes = len(client.get(f"/pacientes/{pid}/visitas", headers=_auth(tok)).json())

    client.post(
        "/registros-visita",
        json={"paciente_id": pid, "ficha_tipo": "livre", "status": "visitado"},
        headers=_auth(tok),
    )
    n_visitas_dp = len(client.get(f"/pacientes/{pid}/visitas", headers=_auth(tok)).json())
    assert n_visitas_dp == n_visitas_antes + 1


def test_acs_edita_proprio_registro_mas_nao_de_outro(client: TestClient) -> None:
    # acs1 cria
    tok1 = _login(client, "acs1")
    pacs = client.get("/pacientes?limit=2000", headers=_auth(tok1)).json()
    pid = pacs[0]["id"]
    r = client.post(
        "/registros-visita",
        json={"paciente_id": pid, "ficha_tipo": "livre", "respostas": {"observacoes": "v1"}},
        headers=_auth(tok1),
    )
    reg_id = r.json()["id"]
    # acs1 edita — OK
    r1 = client.patch(
        f"/registros-visita/{reg_id}",
        json={"resumo": "novo resumo"},
        headers=_auth(tok1),
    )
    assert r1.status_code == 200
    assert r1.json()["resumo"] == "novo resumo"

    # acs2 tenta editar — 403
    tok2 = _login(client, "acs2")
    r2 = client.patch(
        f"/registros-visita/{reg_id}",
        json={"resumo": "intruso"},
        headers=_auth(tok2),
    )
    assert r2.status_code == 403

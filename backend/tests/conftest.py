"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlmodel import Session

from app.core.config import settings


@pytest.fixture
def db_session() -> Session:
    """Sessão SQLModel apontando para a engine corrente (já isolada)."""
    import app.db.session as session_mod

    return Session(session_mod.engine)


@pytest.fixture
def parquets_sinteticos(tmp_path: Path) -> Path:
    """Cria um diretório temporário com os 4 parquets em formato mínimo válido.

    Pacientes têm coordenadas dentro do bounding box do RJ; uma linha de
    cada arquivo contém anomalias (outlier, nulo crítico, duplicado)
    para exercer as ramificações do importer.
    """
    # equipes
    df_eq = pd.DataFrame(
        [
            {"equipe_id": "EQ1", "endereco_latitude": -22.95, "endereco_longitude": -43.20},
            {"equipe_id": "EQ2", "endereco_latitude": -22.90, "endereco_longitude": -43.30},
        ]
    )
    df_eq.to_parquet(tmp_path / "equipes_anonimizadas.parquet")

    # pacientes — inclui outlier (lat fora do RJ), nulo crítico (equipe_id) e duplicado
    rows = []
    for i in range(40):
        rows.append(
            {
                "paciente_id": f"P{i:03d}",
                "equipe_id": "EQ1" if i % 2 == 0 else "EQ2",
                "unidade_id": "U1",
                "faixa_etaria": "19-45",
                "sexo": "Feminino" if i % 3 == 0 else "Masculino",
                "raca_cor": "Parda",
                "situacao_vulnerabilidade": i % 7 == 0,
                "endereco_longitude": -43.20 + (i * 0.001),
                "endereco_latitude": -22.95 + (i * 0.001),
                "hipertenso": i % 4 == 0,
                "diabetico": i % 5 == 0,
                "gestacao": i % 11 == 0,
            }
        )
    # outlier (fora do RJ)
    rows.append(
        {
            "paciente_id": "P_OUT",
            "equipe_id": "EQ1",
            "unidade_id": "U1",
            "faixa_etaria": "19-45",
            "sexo": "Feminino",
            "raca_cor": "Parda",
            "situacao_vulnerabilidade": False,
            "endereco_longitude": -10.0,
            "endereco_latitude": 0.0,
            "hipertenso": False,
            "diabetico": False,
            "gestacao": False,
        }
    )
    # nulo crítico — equipe_id None
    rows.append(
        {
            "paciente_id": "P_NULL",
            "equipe_id": None,
            "unidade_id": "U1",
            "faixa_etaria": "19-45",
            "sexo": "Masculino",
            "raca_cor": None,
            "situacao_vulnerabilidade": False,
            "endereco_longitude": -43.20,
            "endereco_latitude": -22.95,
            "hipertenso": False,
            "diabetico": False,
            "gestacao": False,
        }
    )
    # duplicado
    rows.append(rows[0])
    pd.DataFrame(rows).to_parquet(tmp_path / "pacientes_anonimizados.parquet")

    # visitas
    visitas = []
    for i in range(20):
        visitas.append(
            {
                "profissional_id": f"PROF{i % 3}",
                "registrados_em": "2025-03-03",
                "ordem_visita_dia": i + 1,
                "paciente_id": f"P{i:03d}",
            }
        )
    # duplicado
    visitas.append(visitas[0])
    pd.DataFrame(visitas).to_parquet(tmp_path / "visitas_anonimizadas.parquet")

    # eventos clínicos
    eventos = []
    for i in range(15):
        eventos.append(
            {
                "paciente_id": f"P{i:03d}",
                "tipo": "agendamento" if i % 2 == 0 else "urgencia-emergencia-ou-internacao",
                "data_referencia": "2025-04-15",
            }
        )
    # duplicado exato
    eventos.append(eventos[0])
    pd.DataFrame(eventos).to_parquet(tmp_path / "eventos_clinicos_anonimizados.parquet")

    return tmp_path


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path_factory, monkeypatch):
    """Cada teste roda contra um SQLite temporário próprio (isolamento)."""
    import app.db.session as session_mod
    from app.db import models  # noqa: F401 — registra metadata

    tdir = tmp_path_factory.mktemp("dbdata")
    db_path = tdir / "saude.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    # Reconstrói a engine para apontar para o SQLite isolado.
    new_engine = session_mod._build_engine()
    monkeypatch.setattr(session_mod, "engine", new_engine)

    # Reflete a nova engine nos módulos que a importaram por nome.
    import app.db as db_pkg
    import app.importers.parquets as imp_mod
    import app.importers.seed_users as seed_mod
    monkeypatch.setattr(db_pkg, "engine", new_engine, raising=False)
    monkeypatch.setattr(imp_mod, "engine", new_engine, raising=False)
    monkeypatch.setattr(seed_mod, "engine", new_engine, raising=False)

    yield

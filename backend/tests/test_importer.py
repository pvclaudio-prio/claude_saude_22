"""Testes do importer dos parquets.

Cobrem: schema, nulos críticos, duplicados, outliers, contagens, FK e
geração do quality_report.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlmodel import Session, select

from app.db.models import (
    AreaProgramatica,
    Equipe,
    EventoClinico,
    Paciente,
    Profissional,
    Visita,
)
from app.importers.parquets import (
    ImportError_,
    carregar_e_validar,
    importar,
)
from app.services.clustering import ClusteringConfig


def test_schema_validation_rejeita_colunas_faltantes(tmp_path: Path) -> None:
    """Faltando coluna obrigatória → ImportError_ explícito."""
    df = pd.DataFrame([{"equipe_id": "X"}])  # falta lat/lon
    df.to_parquet(tmp_path / "equipes_anonimizadas.parquet")
    # cria os demais com schema mínimo só para não falhar na leitura
    pd.DataFrame(
        columns=[
            "paciente_id", "equipe_id", "unidade_id", "faixa_etaria", "sexo",
            "raca_cor", "situacao_vulnerabilidade", "endereco_longitude",
            "endereco_latitude", "hipertenso", "diabetico", "gestacao",
        ]
    ).to_parquet(tmp_path / "pacientes_anonimizados.parquet")
    pd.DataFrame(
        columns=["profissional_id", "registrados_em", "ordem_visita_dia", "paciente_id"]
    ).to_parquet(tmp_path / "visitas_anonimizadas.parquet")
    pd.DataFrame(
        columns=["paciente_id", "tipo", "data_referencia"]
    ).to_parquet(tmp_path / "eventos_clinicos_anonimizados.parquet")

    with pytest.raises(ImportError_):
        carregar_e_validar(tmp_path)


def test_importar_basico_com_dados_sinteticos(parquets_sinteticos: Path) -> None:
    """Importação completa com fixture sintética. Garante todas as ramificações."""
    report = importar(
        samples_dir=parquets_sinteticos,
        cfg=ClusteringConfig(n_aps=2, n_bairros=4),
    )

    # quality_report
    pac = report["fontes"]["pacientes"]
    assert pac["linhas_entrada"] == 43  # 40 + outlier + nulo + dup
    assert pac["nulos_criticos_descartados"] == 1
    assert pac["duplicados_descartados"] == 1
    assert pac["outliers_geograficos_marcados"] == 1
    # 40 (válidos) + 1 outlier marcado (mas não descartado) = 41 saída
    assert pac["linhas_saida"] == 41

    eventos = report["fontes"]["eventos_clinicos"]
    assert eventos["duplicados_descartados"] == 1

    # totais persistidos
    totais = report["totais_persistidos"]
    assert totais["equipes"] == 2
    assert totais["pacientes"] == 41
    # 20 visitas + 1 duplicado = 21 entrada; 20 únicas
    assert totais["visitas"] == 20
    assert totais["eventos_clinicos"] == 15

    # clustering criou as APs configuradas
    assert report["clustering"]["n_aps"] == 2
    assert report["clustering"]["n_bairros"] == 4


def test_pacientes_outliers_sao_marcados_nao_apagados(
    parquets_sinteticos: Path, db_session: Session
) -> None:
    """Outlier geográfico deve ficar no banco com `coordenada_outlier=True`."""
    importar(
        samples_dir=parquets_sinteticos,
        cfg=ClusteringConfig(n_aps=2, n_bairros=4),
    )
    with db_session as session:
        outliers = session.exec(
            select(Paciente).where(Paciente.coordenada_outlier == True)  # noqa: E712
        ).all()
        assert len(outliers) == 1
        assert outliers[0].hash_id == "P_OUT"


def test_visitas_respeitam_fk_e_perfis_derivados(
    parquets_sinteticos: Path, db_session: Session
) -> None:
    """Profissionais devem ter sido derivados das visitas e vinculados à equipe modal."""
    importar(samples_dir=parquets_sinteticos, cfg=ClusteringConfig(n_aps=2, n_bairros=4))
    with db_session as session:
        profs = session.exec(select(Profissional)).all()
        assert len(profs) == 3  # PROF0, PROF1, PROF2
        # cada profissional tem equipe_id setado (a equipe modal dos seus pacientes)
        assert all(p.equipe_id is not None for p in profs)

        # FK das visitas: todas as visitas referenciam paciente/profissional existentes
        visitas = session.exec(select(Visita)).all()
        paciente_ids = {p.id for p in session.exec(select(Paciente)).all()}
        prof_ids = {p.id for p in session.exec(select(Profissional)).all()}
        for v in visitas:
            assert v.paciente_id in paciente_ids
            assert v.profissional_id in prof_ids


def test_eventos_tipos_validos(parquets_sinteticos: Path, db_session: Session) -> None:
    importar(samples_dir=parquets_sinteticos, cfg=ClusteringConfig(n_aps=2, n_bairros=4))
    with db_session as session:
        eventos = session.exec(select(EventoClinico)).all()
        tipos = {e.tipo.value for e in eventos}
        assert tipos.issubset({"agendamento", "urgencia-emergencia-ou-internacao"})


def test_equipes_tem_ap_e_bairro_derivados(
    parquets_sinteticos: Path, db_session: Session
) -> None:
    importar(samples_dir=parquets_sinteticos, cfg=ClusteringConfig(n_aps=2, n_bairros=4))
    with db_session as session:
        equipes = session.exec(select(Equipe)).all()
        assert len(equipes) == 2
        # ambas devem ter pelo menos ap_id setado (algum cluster atribuído)
        assert all(e.ap_id is not None for e in equipes)

        aps = session.exec(select(AreaProgramatica)).all()
        assert all(ap.derivado is True for ap in aps)
        assert all(ap.nome.startswith("AP-") for ap in aps)


def test_dataset_real_disponivel_smoke(tmp_path: Path) -> None:
    """Smoke test contra os parquets reais — só roda se eles existirem.

    Validamos as contagens conhecidas: 49 equipes, ~97.9k pacientes,
    ~159k visitas, ~100k eventos clínicos.
    """
    samples = Path(__file__).resolve().parents[2] / "samples"
    if not (samples / "equipes_anonimizadas.parquet").exists():
        pytest.skip("Parquets reais não disponíveis nesta máquina.")

    report = importar(samples_dir=samples)
    totais = report["totais_persistidos"]
    assert totais["equipes"] == 49
    assert 90_000 < totais["pacientes"] < 100_000
    assert 140_000 < totais["visitas"] < 165_000
    assert 90_000 < totais["eventos_clinicos"] < 105_000

"""Importador dos 4 parquets do dataset Saúde RJ.

Princípios (CLAUDE.md):
- Inspecionar antes de assumir — schema, tipos, nulos, duplicados, outliers
  são todos validados explicitamente.
- Nada é descartado em silêncio — cada descarte vai para o quality_report.
- Outliers geográficos são marcados (não apagados) com flag `coordenada_outlier`.
- Idempotente em escopo de MVP: drop_all + create_all antes de inserir.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlmodel import Session, SQLModel, select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import engine
from app.db.models import (
    AreaProgramatica,
    Bairro,
    Equipe,
    EventoClinico,
    Paciente,
    Profissional,
    TipoEventoClinico,
    Unidade,
    Visita,
)
from app.importers.nomes import (
    apelido_equipe,
    apelido_paciente,
    apelido_profissional,
    apelido_unidade,
)
from app.services.clustering import (
    ClusteringConfig,
    derivar_regioes,
    label_ap,
    label_bairro,
)

log = get_logger("importers.parquets")

# Bounding box do município do RJ (com folga de 0.5°)
RJ_LAT_MIN, RJ_LAT_MAX = -23.5, -22.5
RJ_LON_MIN, RJ_LON_MAX = -43.9, -43.0


# ---------------------------------------------------------------------------
# Schemas esperados (defesa em profundidade)
# ---------------------------------------------------------------------------


SCHEMAS = {
    "equipes": {"equipe_id", "endereco_latitude", "endereco_longitude"},
    "pacientes": {
        "paciente_id", "equipe_id", "unidade_id", "faixa_etaria", "sexo",
        "raca_cor", "situacao_vulnerabilidade", "endereco_longitude",
        "endereco_latitude", "hipertenso", "diabetico", "gestacao",
    },
    "visitas": {"profissional_id", "registrados_em", "ordem_visita_dia", "paciente_id"},
    "eventos_clinicos": {"paciente_id", "tipo", "data_referencia"},
}

CRITICAL_NON_NULL = {
    "equipes": {"equipe_id", "endereco_latitude", "endereco_longitude"},
    "pacientes": {"paciente_id", "equipe_id", "unidade_id"},
    "visitas": {"profissional_id", "registrados_em", "paciente_id"},
    "eventos_clinicos": {"paciente_id", "tipo", "data_referencia"},
}


class ImportError_(Exception):
    """Erro durante a importação (não silenciamos no chamador)."""


def _validate_schema(df: pd.DataFrame, name: str) -> None:
    expected = SCHEMAS[name]
    got = set(df.columns)
    missing = expected - got
    if missing:
        raise ImportError_(f"[{name}] colunas faltantes: {sorted(missing)}")


def _coord_outlier(lat: float | None, lon: float | None) -> bool:
    """Marca lat/lon fora do bounding box do RJ. NaN/None NÃO conta como outlier
    (esse caso é tratado em null-check específico)."""
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return False
    return not (RJ_LAT_MIN <= lat <= RJ_LAT_MAX and RJ_LON_MIN <= lon <= RJ_LON_MAX)


# ---------------------------------------------------------------------------
# Etapa 1 — leitura e validação
# ---------------------------------------------------------------------------


def carregar_e_validar(samples_dir: Path) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Lê os 4 parquets, valida schema/tipos/nulos/duplicados, devolve dfs limpos
    + dicionário de relatório de qualidade."""
    files = {
        "equipes": "equipes_anonimizadas.parquet",
        "pacientes": "pacientes_anonimizados.parquet",
        "visitas": "visitas_anonimizadas.parquet",
        "eventos_clinicos": "eventos_clinicos_anonimizados.parquet",
    }

    dfs: dict[str, pd.DataFrame] = {}
    report: dict[str, Any] = {"gerado_em": datetime.now(UTC).isoformat(), "fontes": {}}

    for key, fname in files.items():
        path = samples_dir / fname
        if not path.exists():
            raise ImportError_(f"Parquet ausente: {path}")
        df = pd.read_parquet(path)

        _validate_schema(df, key)

        entrada = len(df)
        nulos_descartados = 0
        duplicados_descartados = 0
        outliers_marcados = 0
        datas_invalidas = 0

        # Nulos críticos — descartar (registrando)
        crit = list(CRITICAL_NON_NULL[key])
        mask_nulos = df[crit].isna().any(axis=1)
        nulos_descartados = int(mask_nulos.sum())
        df = df.loc[~mask_nulos].copy()

        # Datas — converter e marcar inválidas
        if "registrados_em" in df.columns:
            df["registrados_em"] = pd.to_datetime(df["registrados_em"], errors="coerce")
            mask_d = df["registrados_em"].isna()
            datas_invalidas = int(mask_d.sum())
            df = df.loc[~mask_d].copy()
        if "data_referencia" in df.columns:
            df["data_referencia"] = pd.to_datetime(df["data_referencia"], errors="coerce")
            mask_d = df["data_referencia"].isna()
            datas_invalidas += int(mask_d.sum())
            df = df.loc[~mask_d].copy()

        # Outliers geográficos — marcar (não apagar)
        if {"endereco_latitude", "endereco_longitude"}.issubset(df.columns):
            outlier_mask = df.apply(
                lambda r: _coord_outlier(r["endereco_latitude"], r["endereco_longitude"]),
                axis=1,
            )
            df["__outlier__"] = outlier_mask
            outliers_marcados = int(outlier_mask.sum())

        # Duplicados — definição por tabela
        if key == "pacientes":
            dup_mask = df.duplicated(subset=["paciente_id"], keep="first")
        elif key == "equipes":
            dup_mask = df.duplicated(subset=["equipe_id"], keep="first")
        elif key == "visitas":
            dup_mask = df.duplicated(
                subset=["profissional_id", "paciente_id", "registrados_em", "ordem_visita_dia"],
                keep="first",
            )
        elif key == "eventos_clinicos":
            dup_mask = df.duplicated(
                subset=["paciente_id", "tipo", "data_referencia"], keep="first"
            )
        else:
            dup_mask = pd.Series([False] * len(df))

        duplicados_descartados = int(dup_mask.sum())
        df = df.loc[~dup_mask].copy()

        report["fontes"][key] = {
            "arquivo": str(fname),
            "linhas_entrada": entrada,
            "linhas_saida": len(df),
            "nulos_criticos_descartados": nulos_descartados,
            "datas_invalidas_descartadas": datas_invalidas,
            "duplicados_descartados": duplicados_descartados,
            "outliers_geograficos_marcados": outliers_marcados,
        }
        dfs[key] = df
        log.info(
            "importer.carregado",
            tabela=key,
            entrada=entrada,
            saida=len(df),
            nulos=nulos_descartados,
            duplicados=duplicados_descartados,
            outliers=outliers_marcados,
        )

    return dfs, report


# ---------------------------------------------------------------------------
# Etapa 2 — derivações
# ---------------------------------------------------------------------------


def derivar_profissionais(df_visitas: pd.DataFrame, paciente_to_equipe: dict[str, str]) -> pd.DataFrame:
    """Para cada profissional, atribui a equipe mais frequente entre os pacientes
    que ele visitou. Retorna um DataFrame ``(profissional_id, equipe_id)``."""
    tmp = df_visitas.copy()
    tmp["equipe_id"] = tmp["paciente_id"].map(paciente_to_equipe)
    tmp = tmp.dropna(subset=["equipe_id"])

    if tmp.empty:
        return pd.DataFrame(columns=["profissional_id", "equipe_id"])

    moda = (
        tmp.groupby("profissional_id")["equipe_id"]
        .agg(lambda s: Counter(s).most_common(1)[0][0])
        .reset_index()
    )
    return moda


# ---------------------------------------------------------------------------
# Etapa 3 — persistência
# ---------------------------------------------------------------------------


def _reset_db() -> None:
    """Drop + create — válido para MVP. Em produção: Alembic."""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    log.info("importer.db.reset")


def importar(samples_dir: Path | None = None, cfg: ClusteringConfig | None = None) -> dict[str, Any]:
    """Pipeline completo de importação.

    Args:
        samples_dir: pasta com os parquets. Default: ``<repo>/samples``.
        cfg: configuração de clustering.

    Returns:
        Relatório de qualidade (também salvo em ``data/quality_report.json``).
    """
    samples_dir = samples_dir or Path(__file__).resolve().parents[3] / "samples"
    log.info("importer.start", samples_dir=str(samples_dir))

    dfs, report = carregar_e_validar(samples_dir)
    _reset_db()

    df_eq = dfs["equipes"]
    df_pac = dfs["pacientes"]
    df_vis = dfs["visitas"]
    df_ev = dfs["eventos_clinicos"]

    # ------------- clustering ------------------------------------------------
    cl = derivar_regioes(df_pac, cfg)
    df_pac = df_pac.copy()
    df_pac["__ap__"] = cl.ap_labels
    df_pac["__bairro__"] = cl.bairro_labels
    report["clustering"] = {
        "n_aps": cl.ap_centers.shape[0],
        "n_bairros": cl.bairro_centers.shape[0],
        "pacientes_sem_cluster": int((cl.ap_labels == -1).sum()),
    }

    with Session(engine) as session:
        # ------------- APs --------------------------------------------------
        ap_idx_to_id: dict[int, int] = {}
        for i in range(cl.ap_centers.shape[0]):
            ap = AreaProgramatica(
                nome=label_ap(i),
                derivado=True,
                centro_lat=float(cl.ap_centers[i, 0]),
                centro_lon=float(cl.ap_centers[i, 1]),
            )
            session.add(ap)
            session.flush()
            assert ap.id is not None
            ap_idx_to_id[i] = ap.id

        # ------------- Bairros ---------------------------------------------
        bairro_idx_to_id: dict[int, int] = {}
        for i in range(cl.bairro_centers.shape[0]):
            ap_i = cl.bairro_to_ap.get(i, -1)
            b = Bairro(
                nome=label_bairro(i),
                ap_id=ap_idx_to_id.get(ap_i),
                derivado=True,
                centro_lat=float(cl.bairro_centers[i, 0]),
                centro_lon=float(cl.bairro_centers[i, 1]),
            )
            session.add(b)
            session.flush()
            assert b.id is not None
            bairro_idx_to_id[i] = b.id

        # ------------- Unidades --------------------------------------------
        unidades_unicas = df_pac["unidade_id"].dropna().unique().tolist()
        # AP da unidade = AP modal dos seus pacientes
        unidade_ap_modal = (
            df_pac.dropna(subset=["unidade_id"]).groupby("unidade_id")["__ap__"].agg(
                lambda s: Counter(s).most_common(1)[0][0]
            )
        )
        unidade_lat_lon = (
            df_pac.dropna(subset=["unidade_id"])
            .groupby("unidade_id")[["endereco_latitude", "endereco_longitude"]]
            .mean()
        )
        unidade_hash_to_id: dict[str, int] = {}
        for h in unidades_unicas:
            ap_i = int(unidade_ap_modal.get(h, -1))
            lat = float(unidade_lat_lon.loc[h, "endereco_latitude"])
            lon = float(unidade_lat_lon.loc[h, "endereco_longitude"])
            u = Unidade(
                hash_id=h,
                nome_display=apelido_unidade(h),
                ap_id=ap_idx_to_id.get(ap_i),
                centro_lat=lat,
                centro_lon=lon,
            )
            session.add(u)
            session.flush()
            assert u.id is not None
            unidade_hash_to_id[h] = u.id

        # ------------- Equipes ---------------------------------------------
        # equipe → unidade: pegamos a unidade modal entre seus pacientes
        equipe_unidade_modal = (
            df_pac.dropna(subset=["equipe_id", "unidade_id"])
            .groupby("equipe_id")["unidade_id"]
            .agg(lambda s: Counter(s).most_common(1)[0][0])
        )
        equipe_ap_modal = (
            df_pac.dropna(subset=["equipe_id"]).groupby("equipe_id")["__ap__"].agg(
                lambda s: Counter(s).most_common(1)[0][0]
            )
        )
        equipe_bairro_modal = (
            df_pac.dropna(subset=["equipe_id"]).groupby("equipe_id")["__bairro__"].agg(
                lambda s: Counter(s).most_common(1)[0][0]
            )
        )
        equipe_hash_to_id: dict[str, int] = {}
        for _, row in df_eq.iterrows():
            h = row["equipe_id"]
            uid = unidade_hash_to_id.get(equipe_unidade_modal.get(h, ""))
            ap_i = int(equipe_ap_modal.get(h, -1))
            b_i = int(equipe_bairro_modal.get(h, -1))
            e = Equipe(
                hash_id=h,
                nome_display=apelido_equipe(h),
                unidade_id=uid,
                ap_id=ap_idx_to_id.get(ap_i),
                bairro_id=bairro_idx_to_id.get(b_i),
                sede_lat=float(row["endereco_latitude"]),
                sede_lon=float(row["endereco_longitude"]),
            )
            session.add(e)
            session.flush()
            assert e.id is not None
            equipe_hash_to_id[h] = e.id

        # ------------- Pacientes -------------------------------------------
        # paciente_hash -> equipe_hash, para usar mais adiante
        paciente_to_equipe_hash: dict[str, str] = dict(zip(df_pac["paciente_id"], df_pac["equipe_id"]))

        paciente_hash_to_id: dict[str, int] = {}
        # Bulk: construir lista e usar add_all + flush em batches
        BATCH = 5000
        batch: list[Paciente] = []
        for _, row in df_pac.iterrows():
            ap_i = int(row["__ap__"])
            b_i = int(row["__bairro__"])
            equipe_id = equipe_hash_to_id.get(row["equipe_id"])
            unidade_id = unidade_hash_to_id.get(row["unidade_id"])
            outlier = bool(row.get("__outlier__", False))
            p = Paciente(
                hash_id=row["paciente_id"],
                nome_display=apelido_paciente(row["paciente_id"]),
                equipe_id=equipe_id,
                unidade_id=unidade_id,
                ap_id=ap_idx_to_id.get(ap_i),
                bairro_id=bairro_idx_to_id.get(b_i),
                faixa_etaria=str(row["faixa_etaria"]),
                sexo=str(row["sexo"]),
                raca_cor=str(row["raca_cor"]) if not pd.isna(row["raca_cor"]) else None,
                situacao_vulnerabilidade=bool(row["situacao_vulnerabilidade"]),
                hipertenso=bool(row["hipertenso"]),
                diabetico=bool(row["diabetico"]),
                gestacao=bool(row["gestacao"]),
                endereco_latitude=float(row["endereco_latitude"]),
                endereco_longitude=float(row["endereco_longitude"]),
                coordenada_outlier=outlier,
            )
            batch.append(p)
            if len(batch) >= BATCH:
                session.add_all(batch)
                session.flush()
                for obj in batch:
                    assert obj.id is not None
                    paciente_hash_to_id[obj.hash_id] = obj.id
                batch = []
        if batch:
            session.add_all(batch)
            session.flush()
            for obj in batch:
                assert obj.id is not None
                paciente_hash_to_id[obj.hash_id] = obj.id

        # ------------- Profissionais ---------------------------------------
        prof_eq = derivar_profissionais(df_vis, paciente_to_equipe_hash)
        prof_hash_to_id: dict[str, int] = {}
        for _, row in prof_eq.iterrows():
            h = row["profissional_id"]
            eq_hash = row["equipe_id"]
            equipe_id = equipe_hash_to_id.get(eq_hash)
            # unidade/AP do profissional = da equipe
            unidade_id: int | None = None
            ap_id: int | None = None
            if equipe_id is not None:
                eq_obj = session.get(Equipe, equipe_id)
                if eq_obj is not None:
                    unidade_id = eq_obj.unidade_id
                    ap_id = eq_obj.ap_id
            p = Profissional(
                hash_id=h,
                nome_display=apelido_profissional(h),
                equipe_id=equipe_id,
                unidade_id=unidade_id,
                ap_id=ap_id,
            )
            session.add(p)
            session.flush()
            assert p.id is not None
            prof_hash_to_id[h] = p.id
        # Profissionais que apareceram em visitas mas cujo paciente não tinha equipe
        for h in df_vis["profissional_id"].unique():
            if h in prof_hash_to_id:
                continue
            p = Profissional(hash_id=h, nome_display=apelido_profissional(h))
            session.add(p)
            session.flush()
            assert p.id is not None
            prof_hash_to_id[h] = p.id

        # ------------- Visitas ---------------------------------------------
        visitas_descartadas_fk = 0
        batch_v: list[Visita] = []
        for _, row in df_vis.iterrows():
            pid = paciente_hash_to_id.get(row["paciente_id"])
            prid = prof_hash_to_id.get(row["profissional_id"])
            if pid is None or prid is None:
                visitas_descartadas_fk += 1
                continue
            data_v = row["registrados_em"]
            if isinstance(data_v, pd.Timestamp):
                data_v = data_v.date()
            ordem = row.get("ordem_visita_dia")
            ordem_int = int(ordem) if ordem is not None and not pd.isna(ordem) else None
            batch_v.append(Visita(paciente_id=pid, profissional_id=prid, data=data_v, ordem_visita_dia=ordem_int))
            if len(batch_v) >= BATCH:
                session.add_all(batch_v)
                session.flush()
                batch_v = []
        if batch_v:
            session.add_all(batch_v)
            session.flush()

        # ------------- Eventos clínicos ------------------------------------
        eventos_descartados_fk = 0
        batch_e: list[EventoClinico] = []
        for _, row in df_ev.iterrows():
            pid = paciente_hash_to_id.get(row["paciente_id"])
            if pid is None:
                eventos_descartados_fk += 1
                continue
            data_e = row["data_referencia"]
            if isinstance(data_e, pd.Timestamp):
                data_e = data_e.date()
            try:
                tipo = TipoEventoClinico(row["tipo"])
            except ValueError:
                eventos_descartados_fk += 1
                continue
            batch_e.append(EventoClinico(paciente_id=pid, tipo=tipo, data_referencia=data_e))
            if len(batch_e) >= BATCH:
                session.add_all(batch_e)
                session.flush()
                batch_e = []
        if batch_e:
            session.add_all(batch_e)
            session.flush()

        session.commit()

        # ------------- contagens finais ------------------------------------
        report["totais_persistidos"] = {
            "areas_programaticas": session.scalar(_count(AreaProgramatica)),
            "bairros": session.scalar(_count(Bairro)),
            "unidades": session.scalar(_count(Unidade)),
            "equipes": session.scalar(_count(Equipe)),
            "profissionais": session.scalar(_count(Profissional)),
            "pacientes": session.scalar(_count(Paciente)),
            "visitas": session.scalar(_count(Visita)),
            "eventos_clinicos": session.scalar(_count(EventoClinico)),
        }
        report["fontes"]["visitas"]["descartadas_fk"] = visitas_descartadas_fk
        report["fontes"]["eventos_clinicos"]["descartadas_fk"] = eventos_descartados_fk

    # ------------- salva relatório ------------------------------------------
    out = settings.data_dir / "quality_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("importer.done", quality_report=str(out), totais=report["totais_persistidos"])
    return report


def _count(model: type[SQLModel]):
    """Helper: select count(*) from <model>."""
    from sqlalchemy import func
    return select(func.count()).select_from(model)

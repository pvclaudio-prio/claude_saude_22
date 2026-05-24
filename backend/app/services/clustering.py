"""Derivação de Áreas Programáticas e Bairros via clustering geográfico.

Os parquets anonimizados **não contêm** bairro nem AP. Para manter o app
navegável (filtros por região, mapa, gestão por AP), inferimos clusters via
KMeans sobre lat/lon dos pacientes e rotulamos como "AP-01..AP-N" e
"Bairro-XX". Toda entidade derivada carrega `derivado=True` — a UI deve
sinalizar isso ao usuário.

Hiperparâmetros são configuráveis. Defaults baseados na realidade do Rio:
- 10 APs oficiais (1.0, 2.1, 2.2, 3.1, 3.2, 3.3, 4.0, 5.1, 5.2, 5.3) → k=10
- ~160 bairros oficiais → k=30 (granularidade menor para o MVP).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from app.core.logging import get_logger

log = get_logger("clustering")


@dataclass(frozen=True)
class ClusteringConfig:
    """Hiperparâmetros do clustering territorial."""

    n_aps: int = 10
    n_bairros: int = 30
    random_state: int = 42


@dataclass
class ClusteringResult:
    """Resultado do clustering — labels alinhados ao DataFrame de entrada."""

    ap_labels: np.ndarray
    bairro_labels: np.ndarray
    ap_centers: np.ndarray  # shape (n_aps, 2) — (lat, lon)
    bairro_centers: np.ndarray  # shape (n_bairros, 2)
    # Map bairro_id -> ap_id (bairro fica sob a AP cujo centroide é mais próximo)
    bairro_to_ap: dict[int, int]


def derivar_regioes(
    df_pacientes: pd.DataFrame,
    cfg: ClusteringConfig | None = None,
) -> ClusteringResult:
    """Roda KMeans sobre lat/lon dos pacientes e retorna labels + centroides.

    Args:
        df_pacientes: DataFrame com colunas ``endereco_latitude`` e
            ``endereco_longitude``. Linhas com NaN são tratadas: recebem label
            -1 e não influenciam os centroides.
        cfg: parâmetros do clustering (defaults razoáveis).

    Returns:
        ClusteringResult com labels (mesmo tamanho do df) e centroides.
    """
    cfg = cfg or ClusteringConfig()

    mask = df_pacientes[["endereco_latitude", "endereco_longitude"]].notna().all(axis=1)
    coords = df_pacientes.loc[mask, ["endereco_latitude", "endereco_longitude"]].to_numpy()

    if len(coords) < max(cfg.n_aps, cfg.n_bairros):
        # fallback — não há dados suficientes para clusterizar
        log.warning(
            "clustering.insufficient_data",
            n_points=len(coords),
            n_aps=cfg.n_aps,
            n_bairros=cfg.n_bairros,
        )
        n = len(df_pacientes)
        return ClusteringResult(
            ap_labels=np.full(n, -1, dtype=int),
            bairro_labels=np.full(n, -1, dtype=int),
            ap_centers=np.zeros((0, 2)),
            bairro_centers=np.zeros((0, 2)),
            bairro_to_ap={},
        )

    # Áreas Programáticas — granularidade macro
    km_ap = KMeans(n_clusters=cfg.n_aps, random_state=cfg.random_state, n_init=10).fit(coords)
    ap_labels_subset = km_ap.labels_

    # Bairros — granularidade fina
    km_b = KMeans(n_clusters=cfg.n_bairros, random_state=cfg.random_state, n_init=10).fit(coords)
    bairro_labels_subset = km_b.labels_

    # Bairro → AP por proximidade do centroide
    bairro_to_ap: dict[int, int] = {}
    for b_id, center in enumerate(km_b.cluster_centers_):
        dists = np.linalg.norm(km_ap.cluster_centers_ - center, axis=1)
        bairro_to_ap[b_id] = int(np.argmin(dists))

    # Hidratar labels de volta no shape original (linhas sem coordenada → -1)
    ap_labels = np.full(len(df_pacientes), -1, dtype=int)
    bairro_labels = np.full(len(df_pacientes), -1, dtype=int)
    ap_labels[mask.to_numpy()] = ap_labels_subset
    bairro_labels[mask.to_numpy()] = bairro_labels_subset

    log.info(
        "clustering.done",
        n_points=len(coords),
        n_aps=cfg.n_aps,
        n_bairros=cfg.n_bairros,
        inertia_ap=float(km_ap.inertia_),
        inertia_bairro=float(km_b.inertia_),
    )

    return ClusteringResult(
        ap_labels=ap_labels,
        bairro_labels=bairro_labels,
        ap_centers=km_ap.cluster_centers_,
        bairro_centers=km_b.cluster_centers_,
        bairro_to_ap=bairro_to_ap,
    )


def label_ap(ap_idx: int) -> str:
    """Rotula AP derivada — começa em AP-01."""
    return f"AP-{ap_idx + 1:02d}" if ap_idx >= 0 else "AP-ND"


def label_bairro(b_idx: int) -> str:
    """Rotula bairro derivado — começa em Bairro-01."""
    return f"Bairro-{b_idx + 1:02d}" if b_idx >= 0 else "Bairro-ND"

"""CLI de ingestão.

Uso:
    python -m scripts.ingest [--samples-dir PATH] [--n-aps N] [--n-bairros N]

Cria o SQLite, importa os parquets, deriva AP/bairro, semeia usuários demo
e gera ``data/quality_report.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.importers.parquets import importar
from app.importers.seed_planner import seed_planner_acs_demo
from app.importers.seed_users import seed_demo_users
from app.services.clustering import ClusteringConfig
from app.services.risk_score import recalcular_todos


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    log = get_logger("scripts.ingest")

    parser = argparse.ArgumentParser(description="Ingestão dos parquets Saúde RJ.")
    parser.add_argument("--samples-dir", type=Path, default=None)
    parser.add_argument("--n-aps", type=int, default=10)
    parser.add_argument("--n-bairros", type=int, default=30)
    parser.add_argument("--n-acs", type=int, default=5)
    parser.add_argument("--dias-planner", type=int, default=6)
    parser.add_argument("--skip-risco", action="store_true", help="Pula recálculo de risco")
    parser.add_argument("--skip-planner", action="store_true", help="Pula seed do planner")
    args = parser.parse_args(argv)

    try:
        report = importar(
            samples_dir=args.samples_dir,
            cfg=ClusteringConfig(n_aps=args.n_aps, n_bairros=args.n_bairros),
        )
        users = seed_demo_users(n_acs=args.n_acs)
        report["usuarios_demo"] = users

        if not args.skip_risco:
            from sqlmodel import Session

            from app.db.session import engine

            with Session(engine) as s:
                n = recalcular_todos(s)
            report["risco_recalculado_pacientes"] = n

        if not args.skip_planner:
            total_rotas = seed_planner_acs_demo(dias=args.dias_planner)
            report["planner_rotas_dia_geradas"] = total_rotas

        out = settings.data_dir / "quality_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(
            "ingest.complete",
            quality_report=str(out),
            usuarios_demo=list(users.keys()),
            etapas=["importar", "seed_users",
                    *(["risco"] if not args.skip_risco else []),
                    *(["planner"] if not args.skip_planner else [])],
        )
    except Exception:
        log.exception("ingest.failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

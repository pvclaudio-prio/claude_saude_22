"""Engine SQLite + dependência de sessão.

Decisões:
- Uma única engine global, criada a partir de `settings.database_url`.
- `check_same_thread=False` para permitir que o pool seja usado em handlers async.
- `init_db()` cria as tabelas a partir do `SQLModel.metadata` — usado por
  scripts (ingest, testes). Em produção real usaríamos Alembic; para MVP
  o reset-and-create é suficiente.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("db.engine")


def _build_engine() -> Engine:
    """Cria a engine SQLAlchemy configurada para SQLite."""
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    eng = create_engine(
        settings.database_url,
        echo=False,
        connect_args=connect_args,
    )

    # Habilita foreign keys no SQLite (desligadas por default).
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _enable_fk(dbapi_conn, _conn_record) -> None:  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine: Engine = _build_engine()


def init_db() -> None:
    """Cria todas as tabelas do `SQLModel.metadata`.

    Chamado pelo `scripts/ingest.py` e pelos testes. Idempotente.
    """
    # Importa models para garantir registro no metadata.
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    log.info("db.init_db.created", url=settings.database_url)


def get_session() -> Iterator[Session]:
    """Dependência FastAPI — abre/fecha sessão por request."""
    with Session(engine) as session:
        yield session

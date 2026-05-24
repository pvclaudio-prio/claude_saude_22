"""Camada de banco — engine, sessão e models.

`engine` é a instância global do SQLAlchemy. Mantida em ``app.db.session``
para não mascarar o nome do submódulo (a armadilha clássica de chamar
o submódulo de ``engine`` e reexportar a instância com o mesmo nome).
"""

from app.db.session import engine, get_session, init_db
from app.db import models  # noqa: F401 — registra os modelos no metadata

__all__ = ["engine", "get_session", "init_db", "models"]

"""Testes mínimos do bootstrap — garantem que app carrega e config é tipada."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_settings_has_required_fields() -> None:
    """Configurações carregam com defaults sem explodir."""
    assert settings.anthropic_model
    assert settings.database_url.startswith("sqlite")
    assert isinstance(settings.cors_origins, list)


def test_health_endpoint() -> None:
    """Endpoint /health responde 200."""
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

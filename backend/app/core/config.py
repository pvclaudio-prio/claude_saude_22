"""Configurações da aplicação (carregadas de variáveis de ambiente).

Usar `pydantic-settings` para validar e tipar todas as variáveis no boot.
A API key da Anthropic vive **apenas aqui no backend** — nunca no frontend.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Pasta raiz do repo (resolve dois níveis acima de app/core/config.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Carrega manualmente .env da raiz (mais confiável que o suporte built-in
# do pydantic-settings em ambientes Windows com OneDrive).
for _env_path in [_REPO_ROOT / ".env", _REPO_ROOT / "backend" / ".env"]:
    if _env_path.exists():
        # override=True: o .env do projeto sobrepõe variáveis pré-existentes do
        # shell (importante em Windows onde ANTHROPIC_API_KEY pode estar vazia
        # no ambiente do usuário).
        load_dotenv(_env_path, override=True)


class Settings(BaseSettings):
    """Configurações globais lidas das env vars do processo."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Claude ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    anthropic_version: str = Field(default="2023-06-01", alias="ANTHROPIC_VERSION")

    # --- DB ---
    database_url: str = Field(default="sqlite:///./data/saude.db", alias="DATABASE_URL")

    # --- API ---
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="API_CORS_ORIGINS",
    )

    # --- Auth ---
    auth_secret: str = Field(default="demo-secret", alias="AUTH_SECRET")
    auth_token_ttl_min: int = Field(default=480, alias="AUTH_TOKEN_TTL_MIN")

    # --- RAG ---
    embeddings_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDINGS_MODEL",
    )
    chroma_path: str = Field(default="./data/chroma", alias="CHROMA_PATH")

    # --- STT ---
    whisper_model: str = Field(default="small", alias="WHISPER_MODEL")
    whisper_device: str = Field(default="cpu", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="WHISPER_COMPUTE_TYPE")

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=False, alias="LOG_JSON")

    @property
    def cors_origins(self) -> list[str]:
        """Lista de origens CORS permitidas."""
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def data_dir(self) -> Path:
        """Diretório onde ficam o SQLite, Chroma e relatórios — criado no boot."""
        d = Path(__file__).resolve().parents[2] / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton de configurações."""
    return Settings()


settings = get_settings()

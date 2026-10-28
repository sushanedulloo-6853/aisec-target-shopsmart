"""Runtime settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'shopsmart.db'}")
    )

    # auth
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "shopsmart-dev-jwt-secret-2024"))
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("JWT_TTL_MINUTES", "720")))

    # OpenAI
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL") or None)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-6-luna"))
    openai_embedding_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    )

    # vector store
    chroma_dir: str = field(default_factory=lambda: os.getenv("CHROMA_DIR", str(BASE_DIR / "data" / "chroma")))
    chroma_collection: str = field(default_factory=lambda: os.getenv("CHROMA_COLLECTION", "shopsmart_kb"))
    policies_dir: str = field(default_factory=lambda: os.getenv("POLICIES_DIR", str(BASE_DIR / "data" / "policies")))

    # email
    mail_from: str = field(default_factory=lambda: os.getenv("MAIL_FROM", "no-reply@shopsmart.example"))
    mail_dry_run: bool = field(default_factory=lambda: _bool("MAIL_DRY_RUN", True))

    log_dir: str = field(default_factory=lambda: os.getenv("LOG_DIR", str(BASE_DIR / "logs")))
    public_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()

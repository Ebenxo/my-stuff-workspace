"""Process-level configuration (environment / .env). User-level settings live in the database."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import default_home

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXUS_", env_file=".env", extra="ignore")

    home: Path = Field(default_factory=default_home)
    host: str = "127.0.0.1"
    port: int = 8765
    allow_non_loopback: bool = False
    api_token: SecretStr | None = None
    allowed_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_ORIGINS))
    dev: bool = False
    log_level: str = "INFO"
    rate_limit_enabled: bool = True
    # Start scheduled workflows. Tests switch it off and call Scheduler.tick() themselves.
    scheduler_enabled: bool = True
    # Provider used when the user has none configured. Only "demo" is accepted, and only explicitly.
    enable_demo_provider: bool = True

    @model_validator(mode="after")
    def _loopback_only(self) -> Settings:
        if self.host not in LOOPBACK_HOSTS and not self.allow_non_loopback:
            raise ValueError(
                f"NEXUS_HOST={self.host!r} is not a loopback address. NEXUS OS binds to loopback "
                "only; set NEXUS_ALLOW_NON_LOOPBACK=true to override (not recommended)."
            )
        return self

    @property
    def db_path(self) -> Path:
        return self.home / "nexus.db"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"

    @property
    def sync_db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def default_workspace_root(self) -> Path:
        return self.home / "workspace"

    @property
    def token_path(self) -> Path:
        return self.home / "api_token"

    @property
    def allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"[::1]:{self.port}"}

    def ensure_home(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)

    def resolve_api_token(self) -> str:
        """Token from env, else the persisted per-install token (created on first use, mode 0600)."""
        if self.api_token is not None:
            value = self.api_token.get_secret_value()
            if len(value) < 16:
                raise ValueError("NEXUS_API_TOKEN must be at least 16 characters")
            return value
        self.ensure_home()
        path = self.token_path
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if len(existing) >= 32:
                return existing
        token = secrets.token_urlsafe(32)
        _write_private(path, token)
        return token


def _write_private(path: Path, content: str) -> None:
    import os

    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)

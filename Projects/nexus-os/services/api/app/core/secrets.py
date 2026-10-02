"""Secret storage. Keys are write-only from the API; the database only stores a reference name."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.:\-]{0,127}$")
SERVICE = "nexus-os"


class SecretStore(Protocol):
    kind: str

    async def get(self, name: str) -> str | None: ...
    async def set(self, name: str, value: str) -> None: ...
    async def delete(self, name: str) -> None: ...
    def describe(self) -> str: ...


def _check_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid secret name {name!r}")


class MemorySecretStore:
    """Non-persistent store for tests."""

    kind = "memory"

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, name: str) -> str | None:
        _check_name(name)
        return self._data.get(name)

    async def set(self, name: str, value: str) -> None:
        _check_name(name)
        self._data[name] = value

    async def delete(self, name: str) -> None:
        _check_name(name)
        self._data.pop(name, None)

    def describe(self) -> str:
        return "in-memory (not persisted)"


class FileSecretStore:
    """Fallback when no OS keychain is usable: a private (0600) JSON file in NEXUS_HOME."""

    kind = "file"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.error("secret file unreadable; treating as empty")
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

    def _write(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, self._path)

    async def get(self, name: str) -> str | None:
        _check_name(name)
        async with self._lock:
            return await asyncio.to_thread(lambda: self._read().get(name))

    async def set(self, name: str, value: str) -> None:
        _check_name(name)
        async with self._lock:

            def _op() -> None:
                data = self._read()
                data[name] = value
                self._write(data)

            await asyncio.to_thread(_op)

    async def delete(self, name: str) -> None:
        _check_name(name)
        async with self._lock:

            def _op() -> None:
                data = self._read()
                if data.pop(name, None) is not None:
                    self._write(data)

            await asyncio.to_thread(_op)

    def describe(self) -> str:
        return f"private file {self._path} (mode 0600; no OS keychain available)"


class KeyringSecretStore:
    """OS keychain via ``keyring`` (Windows Credential Manager, macOS Keychain, Secret Service)."""

    kind = "keyring"

    def __init__(self, backend_name: str) -> None:
        self._backend_name = backend_name

    async def get(self, name: str) -> str | None:
        import keyring

        _check_name(name)
        return await asyncio.to_thread(keyring.get_password, SERVICE, name)

    async def set(self, name: str, value: str) -> None:
        import keyring

        _check_name(name)
        await asyncio.to_thread(keyring.set_password, SERVICE, name, value)

    async def delete(self, name: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        _check_name(name)
        try:
            await asyncio.to_thread(keyring.delete_password, SERVICE, name)
        except PasswordDeleteError:
            return

    def describe(self) -> str:
        return f"OS keychain ({self._backend_name})"


def _probe_keyring() -> str | None:
    """Return the backend name if the keychain round-trips a value, else None."""
    try:
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring) or backend.priority <= 0:
            return None
        probe = "nexus-os-probe"
        keyring.set_password(SERVICE, probe, "1")
        ok = keyring.get_password(SERVICE, probe) == "1"
        keyring.delete_password(SERVICE, probe)
        return type(backend).__name__ if ok else None
    except Exception:
        return None


def build_secret_store(home: Path) -> SecretStore:
    backend = _probe_keyring()
    if backend is not None:
        return KeyringSecretStore(backend)
    log.warning("No usable OS keychain; secrets fall back to a private file in %s", home)
    return FileSecretStore(home / "secrets.json")

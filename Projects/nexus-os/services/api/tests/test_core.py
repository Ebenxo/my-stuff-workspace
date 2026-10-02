from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from app.core.ids import id_prefix, new_id
from app.core.secrets import FileSecretStore, MemorySecretStore
from app.core.security import constant_time_equals, find_secrets, mask_secret, redact
from app.core.settings import Settings


def test_ids_are_prefixed_sortable_and_unique() -> None:
    ids = [new_id("task") for _ in range(2000)]
    assert len(set(ids)) == 2000
    assert ids == sorted(ids)
    assert all(i.startswith("task_") and len(i) == len("task_") + 26 for i in ids)
    assert id_prefix(ids[0]) == "task"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123", "anthropic_key"),
        ("OPENAI sk-proj-abcdefghijklmnopqrstuvwxyz012345", "openai_key"),
        ("AIzaSyA1234567890abcdefghijklmnopqrstuvwx", "google_api_key"),
        ("ghp_abcdefghijklmnopqrstuvwxyz0123456789ab", "github_token"),
        ("AKIAABCDEFGHIJKLMNOP", "aws_access_key"),
        ("Authorization: Bearer abcdefghijklmnop1234567890", "bearer_token"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk", "jwt"),
        ("password = hunter2hunter2", "credential_assignment"),
        (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END RSA PRIVATE KEY-----",
            "private_key",
        ),
    ],
)
def test_secret_detection_and_redaction(text: str, kind: str) -> None:
    kinds = {m.kind for m in find_secrets(text)}
    assert kind in kinds
    cleaned = redact(text)
    assert "REDACTED" in cleaned
    assert "abcdefghijklmnop1234567890" not in cleaned
    assert "hunter2hunter2" not in cleaned


def test_redact_sensitive_keys_and_nested_structures() -> None:
    data = {
        "api_key": "abc",
        "headers": {"Authorization": "Bearer xyz", "X-Api-Key": "k", "accept": "json"},
        "items": [{"password": "p"}, "ok"],
        "note": "nothing to see",
        "empty_token": "",
    }
    out = redact(data)
    assert out["api_key"] == "[REDACTED]"
    assert out["headers"]["Authorization"] == "[REDACTED]"
    assert out["headers"]["X-Api-Key"] == "[REDACTED]"
    assert out["headers"]["accept"] == "json"
    assert out["items"][0]["password"] == "[REDACTED]"
    assert out["note"] == "nothing to see"
    assert out["empty_token"] == ""


def test_redact_leaves_ordinary_text_alone() -> None:
    text = "Compare three assistants: Claude Code, Cursor and Copilot. Task-42 is done."
    assert redact(text) == text


def test_mask_and_compare() -> None:
    assert mask_secret("sk-abcdefghijklmnop") == "••••mnop"
    assert mask_secret("short") == "••••"
    assert constant_time_equals("a" * 40, "a" * 40)
    assert not constant_time_equals("a" * 40, "a" * 39 + "b")


async def test_memory_secret_store_validates_names() -> None:
    store = MemorySecretStore()
    await store.set("provider:abc", "v")
    assert await store.get("provider:abc") == "v"
    await store.delete("provider:abc")
    assert await store.get("provider:abc") is None
    with pytest.raises(ValueError):
        await store.set("../etc/passwd", "x")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
async def test_file_secret_store_is_private(tmp_path: Path) -> None:
    store = FileSecretStore(tmp_path / "secrets.json")
    await store.set("provider:a", "sekret-value")
    mode = stat.S_IMODE(os.stat(tmp_path / "secrets.json").st_mode)
    assert mode == 0o600
    assert await store.get("provider:a") == "sekret-value"
    await store.delete("provider:a")
    assert await store.get("provider:a") is None


def test_settings_refuse_non_loopback(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(home=tmp_path, host="0.0.0.0", _env_file=None)  # type: ignore[call-arg]
    ok = Settings(home=tmp_path, host="0.0.0.0", allow_non_loopback=True, _env_file=None)  # type: ignore[call-arg]
    assert ok.host == "0.0.0.0"


def test_api_token_is_generated_once_and_private(tmp_path: Path) -> None:
    s = Settings(home=tmp_path / "h", _env_file=None)  # type: ignore[call-arg]
    first = s.resolve_api_token()
    assert len(first) >= 32
    assert s.resolve_api_token() == first
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(s.token_path).st_mode) == 0o600


def test_short_env_token_rejected(tmp_path: Path) -> None:
    s = Settings(home=tmp_path, api_token="short", _env_file=None)  # type: ignore[arg-type,call-arg]
    with pytest.raises(ValueError, match="16"):
        s.resolve_api_token()

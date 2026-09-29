"""Guards SECURITY.md's promise: no credentials in source control."""

from __future__ import annotations

from pathlib import Path

from app.core.security import find_secrets

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRS = {
    "node_modules",
    ".venv",
    "target",
    "dist",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "tests",
    "dev",
}
SKIP_NAMES = {"pnpm-lock.yaml", "uv.lock", "Cargo.lock", "openapi.json", "api.d.ts"}
SCAN_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".json",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".rs",
    ".css",
    ".html",
    ".example",
    ".txt",
}


def _files() -> list[Path]:
    found = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.name in SKIP_NAMES:
            continue
        rel_parts = path.relative_to(PROJECT_ROOT).parts
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if path.suffix in SCAN_SUFFIXES or path.name in {".env.example", ".gitignore"}:
            found.append(path)
    return found


def test_scan_covers_real_files() -> None:
    names = {p.name for p in _files()}
    assert {"settings.py", "BRIEF.md", "package.json"} <= names


def test_no_credentials_committed() -> None:
    offenders: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in find_secrets(text, generic=False):
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.kind}")
    assert offenders == [], "possible secrets in source:\n" + "\n".join(offenders)


def test_env_files_are_gitignored() -> None:
    ignore = (PROJECT_ROOT / ".gitignore").read_text()
    for pattern in (".env", "*.db", "api_token", "secrets.json"):
        assert pattern in ignore
    assert not (PROJECT_ROOT / ".env").exists()

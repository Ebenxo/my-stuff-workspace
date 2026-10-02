#!/usr/bin/env python3
"""Run every quality gate: lint, typecheck, tests, build, API-type drift, import contracts,
dependency audits and the end-to-end walkthrough.

    python scripts/check.py              # everything
    python scripts/check.py --fast       # skip the build, cargo tests, audits and the end-to-end run
    python scripts/check.py --offline    # everything except the dependency audits (they need the internet)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "api"
SKIP_CODE = 3  # a step that cannot run here (e.g. no browser for the end-to-end run) says so with 3


def step(name: str, cmd: list[str], cwd: Path = ROOT) -> str:
    print(f"\n=== {name} ===", flush=True)
    start = time.time()
    result = subprocess.run(cmd, cwd=cwd)  # noqa: S603
    status = "ok" if result.returncode == 0 else "skipped" if result.returncode == SKIP_CODE else "FAILED"
    print(f"--- {name}: {status} ({time.time() - start:.1f}s)", flush=True)
    return status


def main() -> int:
    fast = "--fast" in sys.argv
    offline = "--offline" in sys.argv
    uv = shutil.which("uv") or "uv"
    pnpm = shutil.which("pnpm") or "pnpm"
    cargo = shutil.which("cargo")
    steps: list[tuple[str, list[str], Path]] = [
        ("python: ruff lint", [uv, "run", "ruff", "check", "."], API),
        ("python: ruff format check", [uv, "run", "ruff", "format", "--check", "."], API),
        ("python: mypy (strict)", [uv, "run", "mypy", "app"], API),
        ("python: import contracts", [uv, "run", "lint-imports"], API),
        ("python: tests", [uv, "run", "pytest"], API),
        ("api types up to date", [sys.executable, "scripts/gen_openapi.py", "--check"], ROOT),
        ("ts: eslint", [pnpm, "lint"], ROOT),
        ("ts: typecheck", [pnpm, "typecheck"], ROOT),
        ("ts: tests", [pnpm, "test"], ROOT),
    ]
    if not fast:
        steps.append(("web: production build", [pnpm, "build"], ROOT))
        if cargo:
            steps.append(("desktop sidecar: cargo test", [cargo, "test", "--manifest-path", "apps/desktop/sidecar/Cargo.toml"], ROOT))
        if not offline:
            # Known vulnerabilities in any installed dependency (the API's own package is skipped: it is not on PyPI).
            steps.append(("deps: python audit", [uv, "run", "pip-audit", "--skip-editable", "--progress-spinner", "off"], API))
            steps.append(("deps: js audit", [pnpm, "audit"], ROOT))
        steps.append(("e2e: MVP walkthrough (browser)", [sys.executable, "scripts/e2e.py"], ROOT))
    results = [(name, step(name, cmd, cwd)) for name, cmd, cwd in steps]
    failed = [name for name, status in results if status == "FAILED"]
    skipped = [name for name, status in results if status == "skipped"]
    print()
    if skipped:
        print("Skipped (could not run here): " + ", ".join(skipped))
    print("All checks passed." if not failed else "Failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

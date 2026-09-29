#!/usr/bin/env python3
"""Run every quality gate: lint, typecheck, tests, build, API-type drift, import contracts.

    python scripts/check.py            # everything
    python scripts/check.py --fast     # skip the production build and cargo tests
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "api"


def step(name: str, cmd: list[str], cwd: Path = ROOT) -> bool:
    print(f"\n=== {name} ===", flush=True)
    start = time.time()
    result = subprocess.run(cmd, cwd=cwd)  # noqa: S603
    ok = result.returncode == 0
    print(f"--- {name}: {'ok' if ok else 'FAILED'} ({time.time() - start:.1f}s)", flush=True)
    return ok


def main() -> int:
    fast = "--fast" in sys.argv
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
    failed = [name for name, cmd, cwd in steps if not step(name, cmd, cwd)]
    print("\n" + ("All checks passed." if not failed else "Failed: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

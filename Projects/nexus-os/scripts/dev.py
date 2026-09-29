#!/usr/bin/env python3
"""Run NEXUS OS for development: the Python API and the Vite web app, with one shared token.

    python scripts/dev.py            # API on :8765, web on :5173
    python scripts/dev.py --api-only

Runtime data goes to data/dev (gitignored). The token is generated per launch and given to the
API and to the Vite dev proxy, so it never appears in the browser bundle.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PORT = int(os.environ.get("NEXUS_PORT", "8765"))


def wait_for(url: str, seconds: float = 30) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):  # noqa: S310 - fixed loopback URL
                return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--home", default=str(ROOT / "data" / "dev"))
    args = parser.parse_args()

    token = os.environ.get("NEXUS_API_TOKEN") or secrets.token_urlsafe(32)
    env = {
        **os.environ,
        "NEXUS_HOME": args.home,
        "NEXUS_PORT": str(API_PORT),
        "NEXUS_API_TOKEN": token,
        "NEXUS_DEV": "true",
        "NEXUS_API_URL": f"http://127.0.0.1:{API_PORT}",
    }
    uv = shutil.which("uv")
    pnpm = shutil.which("pnpm")
    if not uv or (not args.api_only and not pnpm):
        print("Need `uv` and `pnpm` on PATH.", file=sys.stderr)
        return 1

    procs: list[subprocess.Popen[bytes]] = []
    try:
        procs.append(
            subprocess.Popen([uv, "run", "--project", "services/api", "nexus", "serve"], cwd=ROOT, env=env)  # noqa: S603
        )
        if not wait_for(f"http://127.0.0.1:{API_PORT}/api/health/ping"):
            print("API did not start.", file=sys.stderr)
            return 1
        print(f"\n  API  http://127.0.0.1:{API_PORT}   data: {args.home}")
        if not args.api_only:
            procs.append(subprocess.Popen([pnpm, "--filter", "@nexus/web", "dev"], cwd=ROOT, env=env))  # type: ignore[arg-type]  # noqa: S603
            print("  Web  http://localhost:5173\n")
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGINT if os.name != "nt" else signal.CTRL_BREAK_EVENT)
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())

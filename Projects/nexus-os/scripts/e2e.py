#!/usr/bin/env python3
"""End-to-end walkthrough of the MVP in a real browser against the real API and web app.

    python scripts/e2e.py            # run it (a fresh data folder, its own ports; nothing else is touched)
    python scripts/e2e.py --keep     # keep the data folder and screenshots afterwards

It starts a stand-in model server (scripts/e2e/standin_model.py), the API and the web dev server on
free ports, then drives scripts/e2e/mvp.mjs with Playwright. Exit codes: 0 passed, 1 failed,
3 skipped because no browser is available (install one with `pnpm exec playwright install chromium`).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIPPED = 3


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for(url: str, seconds: float = 90) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310 - fixed loopback URL
                return True
        except OSError:
            time.sleep(0.3)
    return False


def stop(p: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "nt":
            p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(p.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                p.kill()
            else:
                os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def main() -> int:
    keep = "--keep" in sys.argv
    uv, pnpm, node = shutil.which("uv"), shutil.which("pnpm"), shutil.which("node")
    if not uv or not pnpm or not node:
        print("Need uv, pnpm and node on PATH.", file=sys.stderr)
        return 1
    home = Path(tempfile.mkdtemp(prefix="nexus-e2e-"))
    api_port, web_port, model_port = free_port(), free_port(), free_port()
    token = "e2e-" + os.urandom(12).hex()
    web = f"http://localhost:{web_port}"
    env = {
        **os.environ,
        "NEXUS_HOME": str(home / "data"),
        "NEXUS_PORT": str(api_port),
        "NEXUS_API_TOKEN": token,
        "NEXUS_DEV": "true",
        "NEXUS_API_URL": f"http://127.0.0.1:{api_port}",
        "NEXUS_ALLOWED_ORIGINS": json.dumps([web, f"http://127.0.0.1:{web_port}"]),
        "NEXUS_SCHEDULER_ENABLED": "false",
    }
    group: dict[str, object] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}  # type: ignore[attr-defined]
    )
    logs = home / "logs"
    logs.mkdir()
    procs: list[subprocess.Popen[bytes]] = []

    def spawn(name: str, cmd: list[str]) -> None:
        out = (logs / f"{name}.log").open("wb")
        procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, **group))  # type: ignore[call-overload]  # noqa: S603

    code = 1
    try:
        spawn("model", [sys.executable, "scripts/e2e/standin_model.py", str(model_port)])
        spawn("api", [uv, "run", "--project", "services/api", "nexus", "serve"])
        spawn("web", [pnpm, "--filter", "@nexus/web", "exec", "vite", "--port", str(web_port), "--strictPort"])
        for name, url in (
            ("model", f"http://127.0.0.1:{model_port}/v1/models"),
            ("api", f"http://127.0.0.1:{api_port}/api/health/ping"),
            ("web", web),
        ):
            if not wait_for(url):
                print(f"The {name} server did not start. Log: {logs / (name + '.log')}", file=sys.stderr)
                return 1
        shots = home / "screenshots"
        run = subprocess.run(  # noqa: S603
            [node, "scripts/e2e/mvp.mjs"],
            cwd=ROOT,
            env={
                **env,
                "E2E_WEB": web,
                "E2E_API": f"http://127.0.0.1:{api_port}",
                "E2E_TOKEN": token,
                "E2E_MODEL_URL": f"http://127.0.0.1:{model_port}/v1",
                "E2E_SHOTS": str(shots),
            },
        )
        code = run.returncode
        if code == SKIPPED:
            print("E2E skipped: no browser available. Install one with `pnpm exec playwright install chromium`.")
        elif code != 0:
            keep = True
            print(f"E2E failed. Screenshots and server logs are in {home}", file=sys.stderr)
        elif keep:
            print(f"Screenshots, logs and data kept in {home}")
        return code
    finally:
        for p in reversed(procs):
            stop(p)
        if not keep:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

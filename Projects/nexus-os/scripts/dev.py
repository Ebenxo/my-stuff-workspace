#!/usr/bin/env python3
"""Run NEXUS OS for development: the Python API and the Vite web app, with one shared token.

    python scripts/dev.py               # API on :8765, web on :5173, then opens the browser
    python scripts/dev.py --no-browser
    python scripts/dev.py --api-only

On Windows, double-clicking `start.cmd` runs this. It first checks the tools it needs (and says how
to get any that are missing), installs the project's own packages on the first run, and opens the
browser only once the web app answers.

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
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PORT = int(os.environ.get("NEXUS_PORT", "8765"))
WEB_URL = "http://localhost:5173"

# What each tool is for, and where to get it. Nothing is installed for you: these are system tools.
TOOLS = {
    "uv": "runs the Python API: https://docs.astral.sh/uv/getting-started/installation/",
    "node": "runs the web app (version 20 or newer): https://nodejs.org/",
    "pnpm": "installs the web app's packages: run `corepack enable` once (it comes with Node), or see https://pnpm.io/installation",
}


def missing_tools(need_web: bool) -> list[str]:
    """Plain-words problems with the toolchain; empty when everything needed is there."""
    problems: list[str] = []
    if sys.version_info < (3, 11):  # noqa: UP036 - this runs under whatever Python the person has
        problems.append(f"Python 3.11 or newer (this is {sys.version.split()[0]}): https://www.python.org/downloads/")
    for name in ["uv", "node", "pnpm"] if need_web else ["uv"]:
        if not shutil.which(name):
            problems.append(f"`{name}`, which {TOOLS[name]}")
    node = shutil.which("node")
    if need_web and node:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, check=False).stdout.strip()  # noqa: S603
        major = out.lstrip("v").split(".")[0]
        if major.isdigit() and int(major) < 20:
            problems.append(f"Node 20 or newer (this is {out}): https://nodejs.org/")
    return problems


def first_run_setup(uv: str, pnpm: str | None) -> bool:
    """Install the project's own packages if they are not there yet. Returns False if that failed."""
    steps: list[tuple[str, list[str]]] = []
    if not (ROOT / "services" / "api" / ".venv").exists():
        steps.append(("Setting up the API (first run, takes a minute)", [uv, "sync", "--project", "services/api"]))
    if pnpm and not (ROOT / "node_modules").exists():
        steps.append(("Installing the web app's packages (first run, takes a few minutes)", [pnpm, "install"]))
    for label, cmd in steps:
        print(f"\n  {label}...\n", flush=True)
        if subprocess.run(cmd, cwd=ROOT, check=False).returncode != 0:  # noqa: S603
            shown = " ".join([Path(cmd[0]).stem, *cmd[1:]])
            print(f"\n  That did not work: `{shown}` failed. See the messages above.", file=sys.stderr)
            return False
    return True


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
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser when ready")
    args = parser.parse_args()

    problems = missing_tools(need_web=not args.api_only)
    if problems:
        print("\nNEXUS needs a few tools that are not installed (or not on PATH) yet:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("\nInstall them, open a new terminal window, and run this again.", file=sys.stderr)
        return 1

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
    if not uv or (not args.api_only and not pnpm):  # missing_tools() reported these already
        return 1
    if not first_run_setup(uv, None if args.api_only else pnpm):
        return 1

    if wait_for(f"http://127.0.0.1:{API_PORT}/api/health/ping", seconds=0.5):
        # Otherwise the readiness check below would pass against the old server.
        print(
            f"Something is already answering on port {API_PORT}: NEXUS may already be running in another window "
            f"(then just open {WEB_URL}). Otherwise stop whatever uses that port first.",
            file=sys.stderr,
        )
        return 1

    # Clean up on SIGTERM as well as Ctrl-C (SystemExit runs the finally block below).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    # Each child leads its own process group so shutdown reaches the grandchildren too
    # (pnpm does not forward signals to Vite; uv runs the API as a separate process).
    group: dict[str, object] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    )
    procs: list[subprocess.Popen[bytes]] = []
    try:
        procs.append(
            subprocess.Popen([uv, "run", "--project", "services/api", "nexus", "serve"], cwd=ROOT, env=env, **group)  # type: ignore[call-overload]  # noqa: S603
        )
        if not wait_for(f"http://127.0.0.1:{API_PORT}/api/health/ping"):
            print("API did not start.", file=sys.stderr)
            return 1
        print(f"\n  API  http://127.0.0.1:{API_PORT}   data: {args.home}")
        if not args.api_only:
            procs.append(subprocess.Popen([pnpm, "--filter", "@nexus/web", "dev"], cwd=ROOT, env=env, **group))  # type: ignore[call-overload]  # noqa: S603
            if not wait_for(WEB_URL, seconds=90):
                print("The web app did not start. See the messages above.", file=sys.stderr)
                return 1
            print(f"\n  NEXUS is ready: open {WEB_URL} in your browser on this computer.")
            print("  Keep this window open while you use it. Press Ctrl+C (or close the window) to stop.\n", flush=True)
            if not args.no_browser:
                webbrowser.open(WEB_URL)
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            # SIGTERM, not SIGINT: a launcher started in the background passes an *ignored* SIGINT on
            # to its children. uvicorn and Vite both shut down gracefully on SIGTERM. Signal the whole
            # group even if the direct child already exited: its grandchildren may still be running.
            _signal_group(p, signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                _signal_group(p, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)


def _signal_group(p: subprocess.Popen[bytes], sig: int) -> None:
    try:
        if os.name == "nt":
            p.send_signal(sig)
        else:
            os.killpg(p.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass  # already gone


if __name__ == "__main__":
    raise SystemExit(main())

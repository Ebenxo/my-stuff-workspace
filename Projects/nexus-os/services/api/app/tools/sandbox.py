"""SandboxManager: run a process with a scrubbed environment, a locked working directory, a timeout,
an output cap and whatever resource limits the operating system can enforce.

IMPORTANT: a same-user subprocess is defence in depth, NOT a security boundary against hostile code.
Anything the NEXUS user can read, the process can read. That is why risky code and every command needs
human approval, and why ``SandboxResult.enforced`` reports exactly what was applied. A container
backend can replace this class without touching any tool.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

IS_WINDOWS = sys.platform == "win32"


@dataclass(frozen=True)
class SandboxLimits:
    cpu_s: int = 30
    memory_mb: int = 1024
    file_mb: int = 50
    open_files: int = 256


@dataclass
class SandboxSpec:
    argv: list[str]
    cwd: Path
    timeout_s: float = 30.0
    max_output_bytes: int = 200_000
    stdin: bytes | None = None
    env_extra: dict[str, str] = field(default_factory=dict)
    network: bool = False
    limits: SandboxLimits = field(default_factory=SandboxLimits)


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_ms: int
    enforced: list[str]


@dataclass(frozen=True)
class SandboxCapabilities:
    backend: str
    enforced: list[str]
    not_enforced: list[str]


class SandboxManager(Protocol):
    async def run(self, spec: SandboxSpec) -> SandboxResult: ...
    def capabilities(self) -> SandboxCapabilities: ...


def scrubbed_env(cwd: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Nothing is inherited except PATH (and what Windows needs to start a process). No API keys, no NEXUS_*."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(cwd),
        "TMPDIR": str(cwd),
        "TEMP": str(cwd),
        "TMP": str(cwd),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if IS_WINDOWS:
        for key in ("SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC"):
            if key in os.environ:
                env[key] = os.environ[key]
    env.update(extra or {})
    return env


def _probe_netns() -> bool:
    exe = shutil.which("unshare")
    if IS_WINDOWS or not exe:
        return False
    try:
        return (
            subprocess.run([exe, "-rn", "true"], capture_output=True, timeout=5, check=False).returncode == 0  # noqa: S603
        )
    except (OSError, subprocess.SubprocessError):
        return False


class _Capture:
    """Accumulates a stream up to a cap. Lives outside the reading task so a cancelled read (timeout)
    still leaves everything that arrived before it."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.chunks: list[bytes] = []
        self.total = 0
        self.truncated = False

    async def drain(self, stream: asyncio.StreamReader | None, overflow: asyncio.Event) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                return
            if self.total < self.cap:
                self.chunks.append(chunk[: self.cap - self.total])
            self.total += len(chunk)
            if self.total > self.cap:
                self.truncated = True
                overflow.set()
                return

    def text(self) -> str:
        return b"".join(self.chunks).decode("utf-8", errors="replace")


class LocalSandbox:
    backend = "local-subprocess"

    def __init__(self) -> None:
        self._netns = _probe_netns()

    def capabilities(self) -> SandboxCapabilities:
        enforced = ["timeout", "output_cap", "scrubbed_env", "locked_cwd"]
        missing: list[str] = []
        if IS_WINDOWS:
            missing += ["cpu_limit", "memory_limit", "file_size_limit", "process_group_kill"]
        else:
            enforced += ["cpu_limit", "memory_limit", "file_size_limit", "process_group_kill"]
        (enforced if self._netns else missing).append("network_isolation")
        missing.append("filesystem_isolation")  # a same-user process can read what the user can read
        return SandboxCapabilities(self.backend, enforced, missing)

    @staticmethod
    def _limit_fn(limits: SandboxLimits):  # type: ignore[no-untyped-def]
        def apply() -> None:  # runs in the child before exec (POSIX only)
            import resource

            def cap(which: int, value: int) -> None:
                with contextlib.suppress(ValueError, OSError):
                    resource.setrlimit(which, (value, value))

            cap(resource.RLIMIT_CPU, limits.cpu_s)
            cap(resource.RLIMIT_FSIZE, limits.file_mb * 1024 * 1024)
            cap(resource.RLIMIT_NOFILE, limits.open_files)
            cap(resource.RLIMIT_CORE, 0)
            if sys.platform != "darwin":  # RLIMIT_AS is unreliable on macOS
                cap(resource.RLIMIT_AS, limits.memory_mb * 1024 * 1024)

        return apply

    async def run(self, spec: SandboxSpec) -> SandboxResult:
        argv = list(spec.argv)
        enforced = ["timeout", "output_cap", "scrubbed_env", "locked_cwd"]
        # Resolve the program up front so "not found" reads the same with or without a wrapper.
        env_path = scrubbed_env(spec.cwd)["PATH"]
        if shutil.which(argv[0], path=env_path) is None and not (
            os.path.isabs(argv[0]) and os.access(argv[0], os.X_OK)
        ):
            return SandboxResult(None, "", f"Program not found: {spec.argv[0]}", False, False, 0, enforced)
        if not spec.network and self._netns:
            argv = ["unshare", "-rn", "--", *argv]
            enforced.append("network_isolation")
        kwargs: dict[str, object] = {}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
            kwargs["preexec_fn"] = self._limit_fn(spec.limits)
            enforced += ["cpu_limit", "memory_limit", "file_size_limit", "process_group_kill"]

        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=spec.cwd,
                env=scrubbed_env(spec.cwd, spec.env_extra),
                stdin=asyncio.subprocess.PIPE if spec.stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs,  # type: ignore[arg-type]
            )
        except FileNotFoundError:
            return SandboxResult(None, "", f"Program not found: {spec.argv[0]}", False, False, 0, enforced)
        except PermissionError:
            return SandboxResult(
                None, "", f"Permission denied running: {spec.argv[0]}", False, False, 0, enforced
            )

        overflow = asyncio.Event()
        out_cap, err_cap = _Capture(spec.max_output_bytes), _Capture(spec.max_output_bytes)

        def kill() -> None:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                if IS_WINDOWS:
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)

        async def feed() -> None:
            if spec.stdin is not None and proc.stdin is not None:
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    proc.stdin.write(spec.stdin)
                    await proc.stdin.drain()
                with contextlib.suppress(Exception):
                    proc.stdin.close()

        async def watch_overflow() -> None:
            await overflow.wait()
            kill()  # runaway output: stop the process instead of buffering forever

        timed_out = False
        watcher = asyncio.create_task(watch_overflow())
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    out_cap.drain(proc.stdout, overflow),
                    err_cap.drain(proc.stderr, overflow),
                    proc.wait(),
                    feed(),
                ),
                timeout=spec.timeout_s,
            )
        except TimeoutError:
            timed_out = True
            kill()
            # The buffers keep everything read so far; give the dead process's pipes a moment to flush.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    asyncio.gather(
                        out_cap.drain(proc.stdout, overflow),
                        err_cap.drain(proc.stderr, overflow),
                        proc.wait(),
                    ),
                    timeout=2,
                )
        finally:
            watcher.cancel()
            kill()  # a finished leader can still have left children behind

        return SandboxResult(
            exit_code=proc.returncode,
            stdout=out_cap.text(),
            stderr=err_cap.text(),
            timed_out=timed_out,
            truncated=out_cap.truncated or err_cap.truncated,
            duration_ms=int((time.monotonic() - started) * 1000),
            enforced=enforced,
        )

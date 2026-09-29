from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest

from app.tools.sandbox import LocalSandbox, SandboxLimits, SandboxSpec, scrubbed_env


def process_alive(pid: int) -> bool:
    """True unless the process is gone or a zombie (a killed orphan awaiting a reaper is dead)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return True
    return state != "Z"


posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups and rlimits")
PY = [sys.executable, "-I", "-S", "-B"]


@pytest.fixture
def box() -> LocalSandbox:
    return LocalSandbox()


def spec(tmp_path: Path, code: str, **kw: object) -> SandboxSpec:
    (tmp_path / "main.py").write_text(code)
    return SandboxSpec(argv=[*PY, "main.py"], cwd=tmp_path, **kw)  # type: ignore[arg-type]


async def test_runs_and_captures_output_and_exit_code(box: LocalSandbox, tmp_path: Path) -> None:
    r = await box.run(spec(tmp_path, "import sys\nprint('out')\nprint('err', file=sys.stderr)\nsys.exit(3)"))
    assert (r.exit_code, r.stdout.strip(), r.stderr.strip()) == (3, "out", "err")
    assert not r.timed_out and not r.truncated and r.duration_ms >= 0
    assert {"timeout", "output_cap", "scrubbed_env", "locked_cwd"} <= set(r.enforced)


async def test_stdlib_only_the_apps_own_packages_are_not_importable(
    box: LocalSandbox, tmp_path: Path
) -> None:
    r = await box.run(
        spec(
            tmp_path,
            "import json\ntry:\n    import fastapi\n    print('LEAK')\nexcept ImportError:\n    print('isolated')\ntry:\n    import app\n    print('LEAK2')\nexcept ImportError:\n    print('isolated2')",
        )
    )
    assert r.stdout.split() == ["isolated", "isolated2"]


async def test_environment_is_scrubbed_and_home_is_the_scratch_dir(
    box: LocalSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        "ANTHROPIC_API_KEY": "sk-ant-secret",
        "OPENAI_API_KEY": "sk-secret",
        "NEXUS_API_TOKEN": "tok",
        "AWS_SECRET_ACCESS_KEY": "aws",
        "GITHUB_TOKEN": "gh",
    }.items():
        monkeypatch.setenv(name, value)
    r = await box.run(spec(tmp_path, "import os, json\nprint(json.dumps(dict(os.environ)))"))
    env = json.loads(r.stdout)
    assert not [k for k in env if "KEY" in k or "TOKEN" in k or "SECRET" in k or k.startswith("NEXUS")]
    assert env["HOME"] == str(tmp_path) and env["TMPDIR"] == str(tmp_path)


def test_scrubbed_env_allows_only_explicit_extras(tmp_path: Path) -> None:
    env = scrubbed_env(tmp_path, {"MY_FLAG": "1"})
    assert env["MY_FLAG"] == "1" and "PATH" in env
    assert set(env) >= {"HOME", "TMPDIR", "LANG"}


async def test_working_directory_is_locked(box: LocalSandbox, tmp_path: Path) -> None:
    r = await box.run(spec(tmp_path, "import os\nprint(os.getcwd())"))
    assert Path(r.stdout.strip()).resolve() == tmp_path.resolve()


async def test_timeout_kills_runaway_code_and_reports_it(box: LocalSandbox, tmp_path: Path) -> None:
    started = time.monotonic()
    r = await box.run(spec(tmp_path, "print('started', flush=True)\nwhile True:\n    pass", timeout_s=0.8))
    assert r.timed_out and time.monotonic() - started < 6
    assert "started" in r.stdout  # what was written before the kill is kept


@posix
async def test_timeout_kills_the_whole_process_group_including_children(
    box: LocalSandbox, tmp_path: Path
) -> None:
    marker = tmp_path / "child.pid"
    code = (
        "import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(marker)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    r = await box.run(spec(tmp_path, code, timeout_s=1.5))
    assert r.timed_out
    pid = int(marker.read_text())
    time.sleep(0.3)
    assert not process_alive(pid), "the orphaned child survived the timeout"


@posix
async def test_children_left_behind_by_a_finished_leader_are_killed(
    box: LocalSandbox, tmp_path: Path
) -> None:
    marker = tmp_path / "bg.pid"
    code = (
        "import subprocess, sys\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"open({str(marker)!r}, 'w').write(str(p.pid))\n"
    )
    r = await box.run(spec(tmp_path, code, timeout_s=10))
    assert r.exit_code == 0
    pid = int(marker.read_text())
    time.sleep(0.3)
    assert not process_alive(pid), "a background child outlived its finished parent"


async def test_output_flood_is_capped_and_the_process_stopped(box: LocalSandbox, tmp_path: Path) -> None:
    started = time.monotonic()
    r = await box.run(
        spec(
            tmp_path,
            "import sys\nwhile True:\n    sys.stdout.write('x' * 100000)\n",
            max_output_bytes=50_000,
            timeout_s=20,
        )
    )
    assert r.truncated and len(r.stdout) <= 50_000
    assert not r.timed_out and time.monotonic() - started < 10  # stopped by the cap, not by the timeout


async def test_stdin_is_delivered(box: LocalSandbox, tmp_path: Path) -> None:
    r = await box.run(spec(tmp_path, "import sys\nprint(sys.stdin.read().upper())", stdin=b"hello"))
    assert r.stdout.strip() == "HELLO"


async def test_missing_program_is_a_result_not_an_exception(box: LocalSandbox, tmp_path: Path) -> None:
    r = await box.run(SandboxSpec(argv=["definitely-not-a-real-program-xyz"], cwd=tmp_path))
    assert r.exit_code is None and "not found" in r.stderr.lower()


@posix
async def test_file_size_limit_is_enforced(box: LocalSandbox, tmp_path: Path) -> None:
    r = await box.run(
        spec(
            tmp_path, "open('big.bin','wb').write(b'0' * (5 * 1024 * 1024))", limits=SandboxLimits(file_mb=1)
        )
    )
    assert r.exit_code != 0
    assert (tmp_path / "big.bin").stat().st_size <= 1024 * 1024


@posix
@pytest.mark.skipif(sys.platform == "darwin", reason="RLIMIT_AS unreliable on macOS")
async def test_memory_limit_is_enforced(box: LocalSandbox, tmp_path: Path) -> None:
    r = await box.run(
        spec(
            tmp_path,
            "x = bytearray(2 * 1024 * 1024 * 1024)\nprint('allocated')",
            limits=SandboxLimits(memory_mb=256),
        )
    )
    assert "allocated" not in r.stdout and r.exit_code != 0


async def test_network_is_blocked_when_the_platform_can_isolate_it(box: LocalSandbox, tmp_path: Path) -> None:
    caps = box.capabilities()
    if "network_isolation" not in caps.enforced:
        pytest.skip("network namespaces unavailable here; the report must say so instead")
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        r = await box.run(
            spec(
                tmp_path,
                f"import socket\ntry:\n    socket.create_connection(('127.0.0.1', {port}), timeout=2)\n    print('CONNECTED')\nexcept OSError as e:\n    print('blocked')",
            )
        )
        assert r.stdout.strip() == "blocked" and "network_isolation" in r.enforced
        allowed = await box.run(
            spec(
                tmp_path,
                f"import socket\nsocket.create_connection(('127.0.0.1', {port}), timeout=2)\nprint('CONNECTED')",
                network=True,
            )
        )
        assert "network_isolation" not in allowed.enforced
    finally:
        server.close()


def test_capabilities_are_honest_about_what_is_not_enforced(box: LocalSandbox) -> None:
    caps = box.capabilities()
    assert caps.backend == "local-subprocess"
    assert "filesystem_isolation" in caps.not_enforced  # never claimed
    assert set(caps.enforced).isdisjoint(caps.not_enforced)
    assert ("network_isolation" in caps.enforced) != ("network_isolation" in caps.not_enforced)

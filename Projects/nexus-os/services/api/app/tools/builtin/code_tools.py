"""Code and command execution, always through the SandboxManager."""

from __future__ import annotations

import re
import shutil
import sys
import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.risk import RiskLevel
from app.files.fs import Access, FsError
from app.permissions.policy import RiskAssessment
from app.tools.base import Capability, ToolContext, ToolDefinition, ToolError
from app.tools.command_filter import assess_command
from app.tools.pyrisk import classify_python
from app.tools.sandbox import SandboxLimits, SandboxSpec

PY_ARGV = [sys.executable, "-I", "-S", "-B", "main.py"]  # isolated, no site-packages: standard library only
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class RunPythonArgs(BaseModel):
    code: str = Field(
        description="Python 3 source. Standard library only (json, csv, statistics, math, re, datetime, collections…). "
        "Print results to stdout. Write output files into the working directory.",
        min_length=1,
        max_length=100_000,
    )
    inputs: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Project files to copy into the working directory first, e.g. ['files/data.csv']. Open them by file name.",
    )
    timeout_s: int = Field(default=20, ge=1, le=60)


def _assess_python(ctx: ToolContext, a: RunPythonArgs) -> RiskAssessment:
    risk = classify_python(a.code)
    if risk.risky:
        return RiskAssessment(
            level=RiskLevel.HIGH,
            impact="This code "
            + "; ".join(risk.findings)
            + ". It runs in a restricted process, but a person should read it first.",
        )
    return RiskAssessment(
        level=RiskLevel.MODERATE,
        impact=f"Runs {len(a.code.splitlines())} lines of standard-library Python in a throwaway folder ({a.timeout_s}s limit, no network).",
    )


def _result(r: Any, workdir: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "exit_code": r.exit_code,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "timed_out": r.timed_out,
        "output_truncated": r.truncated,
        "duration_ms": r.duration_ms,
        "workdir": workdir,
        "limits_applied": r.enforced,
    }
    out.update(extra or {})
    return out


async def run_python(ctx: ToolContext, a: RunPythonArgs) -> dict[str, Any]:
    rel = f"temp/run-{uuid.uuid4().hex[:8]}"
    try:
        _, work = ctx.fs.resolve(rel, Access.WRITE)
        work.mkdir(parents=True, exist_ok=False)
        (work / "main.py").write_text(a.code, encoding="utf-8")
        copied: set[str] = {"main.py"}
        for src in a.inputs:
            clean, path = ctx.fs.resolve(src, Access.READ)
            if not path.is_file():
                raise ToolError(f"Input '{clean}' is not a file.", code="not_found")
            if path.stat().st_size > 5_000_000:
                raise ToolError(f"Input '{clean}' is larger than 5 MB.", code="too_large")
            name = _SAFE_NAME.sub("_", path.name) or "input"
            if name in copied:
                raise ToolError(f"Two inputs share the file name '{name}'.", code="invalid_args")
            shutil.copyfile(path, work / name)
            copied.add(name)
    except FsError as e:
        raise ToolError(e.message, code=e.code) from e
    r = await ctx.sandbox.run(
        SandboxSpec(
            argv=PY_ARGV,
            cwd=work,
            timeout_s=a.timeout_s,
            network=False,
            limits=SandboxLimits(cpu_s=a.timeout_s + 5),
        )
    )
    produced = [p for p in sorted(work.iterdir()) if p.is_file() and p.name not in copied][:20]
    outputs = [{"path": f"{rel}/{p.name}", "bytes": p.stat().st_size} for p in produced]
    return _result(r, rel, {"outputs": outputs})


class RunCommandArgs(BaseModel):
    argv: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Program and arguments as a list, e.g. ['git', 'status']. No shell is involved.",
    )
    shell: bool = Field(
        default=False,
        description="Run 'command' through a shell instead (pipes, globs). Always needs approval and is reviewed as text.",
    )
    command: str | None = Field(
        default=None, max_length=4000, description="The shell command text when shell is true."
    )
    cwd: str = Field(
        default="files",
        max_length=300,
        description="Working folder inside the project ('files' or 'temp' and below).",
    )
    timeout_s: int = Field(default=30, ge=1, le=120)
    network: bool = Field(default=False, description="Allow network access. Treated as very high risk.")

    @model_validator(mode="after")
    def _one_form(self) -> RunCommandArgs:
        if self.shell and not (self.command and self.command.strip()):
            raise ValueError("shell=true needs 'command'")
        if not self.shell and not self.argv:
            raise ValueError("give 'argv' (or shell=true with 'command')")
        if any(len(x) > 2000 or "\x00" in x for x in self.argv):
            raise ValueError("an argument is too long or contains an invalid character")
        return self


def _assess_command(ctx: ToolContext, a: RunCommandArgs) -> RiskAssessment:
    base = assess_command(
        a.argv if not a.shell else ["sh"],
        shell_text=a.command if a.shell else None,
        network=a.network,
        cwd=a.cwd,
    )
    if base.deny_reason:
        return base
    try:  # fail before asking a person to approve a command that could never start
        clean, cwd = ctx.fs.resolve(a.cwd, Access.WRITE)
    except FsError as e:
        return RiskAssessment(deny_reason=e.message)
    if not cwd.is_dir():
        return RiskAssessment(deny_reason=f"Working folder '{clean}' does not exist.")
    caps = ctx.sandbox.capabilities()
    note = ""
    if not a.network and "network_isolation" not in caps.enforced:
        note = " WARNING: network isolation is not available on this system, so the command could still reach the network."
    return RiskAssessment(level=base.level, always_ask=True, impact=base.impact + note)


async def run_command(ctx: ToolContext, a: RunCommandArgs) -> dict[str, Any]:
    try:
        clean, cwd = ctx.fs.resolve(a.cwd, Access.WRITE)
    except FsError as e:
        raise ToolError(e.message, code=e.code) from e
    if not cwd.is_dir():
        raise ToolError(f"Working folder '{clean}' does not exist.", code="not_found")
    if a.shell:
        argv = (
            ["cmd", "/c", a.command or ""] if sys.platform == "win32" else ["/bin/sh", "-c", a.command or ""]
        )
    else:
        argv = a.argv
    r = await ctx.sandbox.run(
        SandboxSpec(
            argv=argv,
            cwd=cwd,
            timeout_s=a.timeout_s,
            network=a.network,
            limits=SandboxLimits(cpu_s=a.timeout_s + 5),
        )
    )
    return _result(r, clean)


TOOLS = [
    ToolDefinition(
        "run_python",
        "Run standard-library Python in a restricted, throwaway working folder (no network, time and memory limited). "
        "Good for calculations and data wrangling. Risky code (imports os/subprocess/socket, opens arbitrary files, uses eval) needs approval.",
        RunPythonArgs,
        RiskLevel.MODERATE,
        run_python,
        permissions=frozenset({Capability.CODE_EXEC}),
        assess_risk=_assess_python,
        timeout_s=90,
        max_output_chars=60_000,
    ),
    ToolDefinition(
        "run_command",
        "Run a program with an argument list (no shell) inside the project. Every command needs the user's approval. "
        "Destructive or system-level programs are blocked.",
        RunCommandArgs,
        RiskLevel.HIGH,
        run_command,
        requires_approval=True,
        permissions=frozenset({Capability.PROC_EXEC}),
        assess_risk=_assess_command,
        timeout_s=150,
        max_output_chars=60_000,
        alternatives=("run_python",),
    ),
]

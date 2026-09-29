"""Read-only git inspection through the sandbox. Config and hooks are neutralised."""

from __future__ import annotations

import shutil
from typing import Any

from pydantic import BaseModel, Field

from app.core.risk import RiskLevel
from app.files.fs import Access, FsError
from app.tools.base import Capability, ToolContext, ToolDefinition, ToolError
from app.tools.sandbox import SandboxSpec

# core.fsmonitor and hooksPath can execute programs from a repository's own config: disable them.
GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "--no-pager"]


class RepoArgs(BaseModel):
    repo: str = Field(
        default="files",
        description="Folder containing the git repository, e.g. 'files/my-app'.",
        max_length=300,
    )


class GitDiffArgs(RepoArgs):
    staged: bool = False
    path: str | None = Field(
        default=None, description="Limit the diff to one file or folder.", max_length=300
    )
    stat_only: bool = Field(
        default=False, description="Show a summary of changed files instead of the full diff."
    )


class GitLogArgs(RepoArgs):
    limit: int = Field(default=20, ge=1, le=100)


async def _git(ctx: ToolContext, repo: str, args: list[str], timeout_s: int = 20) -> dict[str, Any]:
    if shutil.which("git") is None:
        raise ToolError("git is not installed on this computer.", code="git_missing")
    try:
        clean, cwd = ctx.fs.resolve(repo, Access.READ)
    except FsError as e:
        raise ToolError(e.message, code=e.code) from e
    if not (cwd / ".git").exists():
        raise ToolError(f"'{clean}' is not a git repository (no .git folder).", code="not_a_repo")
    r = await ctx.sandbox.run(
        SandboxSpec(
            argv=[*GIT, *args],
            cwd=cwd,
            timeout_s=timeout_s,
            network=False,
            env_extra={
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null" if shutil.which("true") else "NUL",
            },
        )
    )
    if r.exit_code not in (0, None) and not r.stdout:
        raise ToolError(r.stderr.strip()[:500] or "git failed.", code="git_error")
    return {"repo": clean, "output": r.stdout, "truncated": r.truncated}


async def git_status(ctx: ToolContext, a: RepoArgs) -> dict[str, Any]:
    return await _git(ctx, a.repo, ["status", "--porcelain=v1", "-b"])


async def git_diff(ctx: ToolContext, a: GitDiffArgs) -> dict[str, Any]:
    args = ["diff", "--no-ext-diff", "--no-textconv", "--no-color"]
    if a.staged:
        args.append("--cached")
    if a.stat_only:
        args.append("--stat")
    if a.path:
        args += ["--", a.path]
    return await _git(ctx, a.repo, args)


async def git_log(ctx: ToolContext, a: GitLogArgs) -> dict[str, Any]:
    return await _git(
        ctx,
        a.repo,
        ["log", "--no-color", f"-n{a.limit}", "--date=short", "--pretty=format:%h%x09%ad%x09%an%x09%s"],
    )


def _mk(name: str, doc: str, schema: type[BaseModel], fn: Any) -> ToolDefinition:
    return ToolDefinition(
        name,
        doc,
        schema,
        RiskLevel.SAFE,
        fn,
        permissions=frozenset({Capability.FS_READ, Capability.PROC_EXEC}),
        returns_untrusted=True,
        source_label=lambda a: f"git:{a.repo}",
        timeout_s=30,
        max_output_chars=60_000,
    )


TOOLS = [
    _mk(
        "git_status",
        "Show the working tree status of a git repository in the project (read-only).",
        RepoArgs,
        git_status,
    ),
    _mk("git_diff", "Show uncommitted changes in a git repository (read-only).", GitDiffArgs, git_diff),
    _mk("git_log", "Show recent commits of a git repository (read-only).", GitLogArgs, git_log),
]

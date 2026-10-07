"""Per-project workspace directories. (Path-guarded file access lives in files/fs.py.)"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_SUBDIRS = ("files", "artifacts", "memory", "temp", ".trash", ".history")


@dataclass(frozen=True)
class DiskUsage:
    total: int
    used: int
    free: int
    workspace_bytes: int


class WorkspaceManager:
    """Owns the on-disk layout: ``<root>/projects/<project_id>/{files,artifacts,memory,temp,...}``."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("workspace root must be an absolute path")
        self.root = root

    def project_rel_path(self, project_id: str) -> str:
        return f"projects/{project_id}"

    def project_dir(self, project_id: str) -> Path:
        return self.root / "projects" / project_id

    def ensure_project(self, project_id: str) -> Path:
        base = self.project_dir(project_id)
        for sub in PROJECT_SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base

    def disk_usage(self) -> DiskUsage:
        self.root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self.root)
        size = 0
        for path in self.root.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    size += path.stat().st_size
            except OSError:
                continue
        return DiskUsage(total=usage.total, used=usage.used, free=usage.free, workspace_bytes=size)

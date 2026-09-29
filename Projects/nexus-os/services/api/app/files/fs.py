"""WorkspaceFS: the only way tools touch project files. Everything is confined to one project root.

Layout under the root: ``files/`` (agent read/write), ``artifacts/`` (read; written via the artifact
store), ``temp/`` (read/write scratch), plus hidden ``.trash``, ``.history`` and ``memory``.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import shutil
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 5_000_000
MAX_PATH_CHARS = 1024
MAX_SEGMENT_CHARS = 255
READ_AREAS = frozenset({"files", "artifacts", "temp"})
WRITE_AREAS = frozenset({"files", "temp"})
HIDDEN_AREAS = frozenset({".trash", ".history", "memory"})
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
_DRIVE = re.compile(r"^[A-Za-z]:")


class FsError(Exception):
    """A refused or failed filesystem operation. ``code`` is stable; the message is user-safe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Access(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class Entry:
    path: str  # relative to the project root, forward slashes
    kind: str  # "file" | "dir"
    size: int
    modified: float


def _clean_relative(rel: str) -> str:
    """Validate and normalise a caller-supplied path. Pure string checks; no filesystem access."""
    if not isinstance(rel, str) or not rel.strip():
        raise FsError("invalid_path", "The path is empty.")
    if "\x00" in rel:
        raise FsError("invalid_path", "The path contains an invalid character.")
    if len(rel) > MAX_PATH_CHARS:
        raise FsError("invalid_path", "The path is too long.")
    text = rel.replace("\\", "/")
    if text.startswith("/") or text.startswith("~") or _DRIVE.match(text):
        raise FsError(
            "outside_workspace",
            "Absolute paths are not allowed. Use a path inside the project, like files/notes.md.",
        )
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise FsError("outside_workspace", "Paths may not go up with '..'.")
    if not parts:
        raise FsError("invalid_path", "The path is empty.")
    for part in parts:
        if len(part) > MAX_SEGMENT_CHARS:
            raise FsError("invalid_path", "A path segment is too long.")
        if _RESERVED.match(part) or part.endswith((".", " ")):
            raise FsError("invalid_path", f"'{part}' is not a valid file name.")
        if any(ord(c) < 32 for c in part):
            raise FsError("invalid_path", "The path contains control characters.")
    return posixpath.normpath("/".join(parts))


class WorkspaceFS:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    # ---- path resolution -----------------------------------------------------------------
    def resolve(
        self, rel: str, access: Access = Access.READ, *, allow_root: bool = False
    ) -> tuple[str, Path]:
        """Return ``(clean_rel, absolute_path)`` or raise. Symlinks and junctions are followed and
        the *real* location must still be inside the project root."""
        clean = _clean_relative(rel) if not (allow_root and rel in ("", ".", "/")) else "."
        if clean == ".":
            return ".", self.root
        area = clean.split("/", 1)[0]
        if area in HIDDEN_AREAS:
            raise FsError("outside_workspace", f"'{area}' is managed by NEXUS and is not accessible.")
        allowed = WRITE_AREAS if access is Access.WRITE else READ_AREAS
        if area not in allowed:
            hint = (
                "Write into files/ or temp/. Create deliverables with create_document."
                if access is Access.WRITE
                else "Read from files/, artifacts/ or temp/."
            )
            raise FsError(
                "area_not_allowed",
                f"'{area}/' is not {'writable' if access is Access.WRITE else 'readable'} here. {hint}",
            )
        candidate = (self.root / clean).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise FsError(
                "outside_workspace", "That path resolves outside the project (a link points elsewhere)."
            ) from None
        # A link inside the project could point into a hidden area; re-check the resolved area.
        real_area = candidate.relative_to(self.root).parts[0] if candidate != self.root else ""
        if real_area in HIDDEN_AREAS:
            raise FsError("outside_workspace", "That path resolves into a protected area.")
        return clean, candidate

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    # ---- reads ---------------------------------------------------------------------------
    def list_dir(self, rel: str = ".", *, limit: int = 500) -> list[Entry]:
        _, path = self.resolve(rel, allow_root=True)
        if path == self.root:
            return [Entry(a, "dir", 0, 0.0) for a in sorted(READ_AREAS) if (self.root / a).is_dir()]
        if not path.is_dir():
            raise FsError("not_a_directory", "That is not a directory.")
        entries: list[Entry] = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith(".") and child.name != ".gitignore":
                continue
            try:
                real = child.resolve()
                real.relative_to(self.root)
                st = child.stat()
            except (ValueError, OSError):
                continue  # a link leaving the workspace is invisible, not an error
            entries.append(
                Entry(
                    self._rel(child),
                    "dir" if child.is_dir() else "file",
                    0 if child.is_dir() else st.st_size,
                    st.st_mtime,
                )
            )
            if len(entries) >= limit:
                break
        return entries

    def read_text(self, rel: str, *, max_bytes: int = MAX_READ_BYTES) -> tuple[str, bool]:
        """(text, truncated). Refuses binary files."""
        clean, path = self.resolve(rel)
        if not path.exists():
            raise FsError("not_found", f"'{clean}' does not exist.")
        if not path.is_file():
            raise FsError("not_a_file", f"'{clean}' is not a file.")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not os.path.samestat(os.fstat(fd), path.stat()):
                raise FsError("changed", "The file changed while it was being opened.")
            with os.fdopen(fd, "rb", closefd=False) as fh:
                raw = fh.read(max_bytes + 1)
        finally:
            os.close(fd)
        if b"\x00" in raw[:8192]:
            raise FsError("binary_file", f"'{clean}' looks like a binary file, so it cannot be read as text.")
        truncated = len(raw) > max_bytes
        return raw[:max_bytes].decode("utf-8", errors="replace"), truncated

    def stat_size(self, rel: str) -> int:
        _, path = self.resolve(rel)
        return path.stat().st_size

    def search(
        self,
        query: str,
        *,
        subdir: str = ".",
        regex: bool = False,
        glob: str | None = None,
        max_results: int = 100,
        max_files: int = 2000,
    ) -> list[dict[str, object]]:
        if not query:
            raise FsError("invalid_query", "The search text is empty.")
        try:
            pattern = re.compile(query if regex else re.escape(query), re.IGNORECASE)
        except re.error as exc:
            raise FsError("invalid_query", f"Invalid regular expression: {exc}") from None
        _, base = self.resolve(subdir, allow_root=True)
        roots = [self.root / a for a in sorted(READ_AREAS)] if base == self.root else [base]
        hits: list[dict[str, object]] = []
        scanned = 0
        for top in roots:
            if not top.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in sorted(filenames):
                    if glob and not Path(name).match(glob):
                        continue
                    scanned += 1
                    if scanned > max_files:
                        return hits
                    file_path = Path(dirpath) / name
                    try:
                        if file_path.stat().st_size > MAX_READ_BYTES or file_path.is_symlink():
                            continue
                        with open(file_path, "rb") as fh:
                            raw = fh.read(MAX_READ_BYTES)
                    except OSError:
                        continue
                    if b"\x00" in raw[:8192]:
                        continue
                    for lineno, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
                        if pattern.search(line):
                            hits.append(
                                {"path": self._rel(file_path), "line": lineno, "text": line.strip()[:200]}
                            )
                            if len(hits) >= max_results:
                                return hits
        return hits

    # ---- writes --------------------------------------------------------------------------
    def _history(self, clean: str, path: Path) -> str | None:
        """Copy the current content aside before it is replaced. Returns the history path."""
        if not path.is_file():
            return None
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
        dest = self.root / ".history" / clean / f"{stamp}-{digest}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        return dest.relative_to(self.root).as_posix()

    def write_text(self, rel: str, content: str, *, overwrite: bool = True) -> dict[str, object]:
        data = content.encode("utf-8")
        if len(data) > MAX_WRITE_BYTES:
            raise FsError("too_large", f"The content is larger than {MAX_WRITE_BYTES // 1_000_000} MB.")
        clean, path = self.resolve(rel, Access.WRITE)
        if path.exists() and path.is_dir():
            raise FsError("is_a_directory", f"'{clean}' is a directory.")
        existed = path.exists()
        if existed and not overwrite:
            raise FsError("exists", f"'{clean}' already exists.")
        path.parent.mkdir(parents=True, exist_ok=True)
        history = self._history(clean, path) if existed else None
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return {"path": clean, "bytes": len(data), "created": not existed, "previous_version": history}

    def mkdir(self, rel: str) -> str:
        clean, path = self.resolve(rel, Access.WRITE)
        if path.exists() and not path.is_dir():
            raise FsError("exists", f"'{clean}' exists and is not a directory.")
        path.mkdir(parents=True, exist_ok=True)
        return clean

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> dict[str, object]:
        s_clean, s_path = self.resolve(src, Access.WRITE)
        d_clean, d_path = self.resolve(dst, Access.WRITE)
        if not s_path.exists():
            raise FsError("not_found", f"'{s_clean}' does not exist.")
        if d_path.exists() and not overwrite:
            raise FsError("exists", f"'{d_clean}' already exists.")
        if d_path.is_dir() and d_path.exists():
            raise FsError("is_a_directory", f"'{d_clean}' is a directory.")
        history = self._history(d_clean, d_path) if d_path.exists() else None
        d_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(s_path, d_path)
        return {"from": s_clean, "to": d_clean, "overwrote": history is not None, "previous_version": history}

    def would_overwrite(self, dst: str) -> bool:
        try:
            _, p = self.resolve(dst, Access.WRITE)
        except FsError:
            return False
        return p.exists()

    def soft_delete(self, rel: str) -> dict[str, object]:
        """Move into ``.trash`` (recoverable). Never unlinks."""
        clean, path = self.resolve(rel, Access.WRITE)
        if not path.exists():
            raise FsError("not_found", f"'{clean}' does not exist.")
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        dest = self.root / ".trash" / f"{stamp}__{clean.replace('/', '__')}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))
        return {"path": clean, "moved_to_trash": dest.relative_to(self.root).as_posix()}

    def exists(self, rel: str) -> bool:
        try:
            _, p = self.resolve(rel)
        except FsError:
            return False
        return p.exists()

"""One NEXUS API per data folder.

Startup does things that are only correct when nothing else is using the same database: it marks
every open agent run as interrupted and cancels their approvals. A second instance pointed at the
same home (a double-launched desktop app, a stray dev server) would do that to runs the first one is
still executing. So the first thing startup does is take an exclusive, OS-level lock on a file in the
home folder. The OS releases it if the process dies, so a crash never leaves a stale lock.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import IO

LOCK_NAME = "nexus.lock"


class InstanceLockedError(RuntimeError):
    """Another NEXUS API is already running with this data folder."""


class InstanceLock:
    def __init__(self, home: Path) -> None:
        self.path = home / LOCK_NAME
        self._fh: IO[str] | None = None

    @property
    def held(self) -> bool:
        return self._fh is not None

    def acquire(self) -> None:
        if self._fh is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")  # noqa: SIM115 - held open for the process lifetime
        try:
            _lock(fh)
        except OSError:
            fh.close()
            raise InstanceLockedError(
                f"Another NEXUS instance is already using {self.path.parent}. "
                "Close it first, or start this one with a different NEXUS_HOME."
            ) from None
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            _unlock(fh)
        finally:
            fh.close()


if sys.platform == "win32":
    import msvcrt

    def _lock(fh: IO[str]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh: IO[str]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fh: IO[str]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh: IO[str]) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

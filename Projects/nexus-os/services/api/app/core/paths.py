"""Filesystem locations for NEXUS runtime data."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir


def default_home() -> Path:
    """The OS-appropriate per-user data directory. Overridden by ``NEXUS_HOME``."""
    return Path(user_data_dir("nexus-os", appauthor=False))

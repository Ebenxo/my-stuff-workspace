"""Provenance: which untrusted sources have influenced this run."""

from __future__ import annotations


class TaintTracker:
    def __init__(self, sources: list[str] | None = None) -> None:
        self._sources: list[str] = list(dict.fromkeys(sources or []))

    def add(self, source: str) -> None:
        if source not in self._sources:
            self._sources.append(source)

    @property
    def tainted(self) -> bool:
        return bool(self._sources)

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    def to_list(self) -> list[str]:
        return list(self._sources)

    @classmethod
    def from_list(cls, items: list[str] | None) -> TaintTracker:
        return cls(items)

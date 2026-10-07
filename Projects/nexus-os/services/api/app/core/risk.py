"""Risk levels. Ordered: SAFE < MODERATE < HIGH < VERY_HIGH."""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    SAFE = "SAFE"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"

    @property
    def rank(self) -> int:
        return _RANK[self]

    def __lt__(self, other: object) -> bool:
        return isinstance(other, RiskLevel) and self.rank < other.rank

    def __le__(self, other: object) -> bool:
        return isinstance(other, RiskLevel) and self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        return isinstance(other, RiskLevel) and self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        return isinstance(other, RiskLevel) and self.rank >= other.rank


_RANK = {RiskLevel.SAFE: 0, RiskLevel.MODERATE: 1, RiskLevel.HIGH: 2, RiskLevel.VERY_HIGH: 3}


def max_risk(*levels: RiskLevel) -> RiskLevel:
    return max(levels, key=lambda r: r.rank)

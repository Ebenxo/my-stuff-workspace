"""TaskGraph: a pure in-memory DAG over task ids and statuses.

Used by the plan validator (on keys) and by the executor (on task ids). No I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.schemas.orchestration import TaskStatus


class CycleError(ValueError):
    def __init__(self, cycle: list[str]) -> None:
        super().__init__(f"dependency cycle: {' -> '.join(cycle)}")
        self.cycle = cycle


# A dependency in one of these states lets its dependents start.
SATISFIED = frozenset({TaskStatus.COMPLETED, TaskStatus.SKIPPED})
# A dependency in one of these states can never satisfy its dependents.
DEAD = frozenset({TaskStatus.FAILED, TaskStatus.CANCELLED})


@dataclass
class TaskGraph:
    deps: dict[str, set[str]] = field(default_factory=dict)
    status: dict[str, TaskStatus] = field(default_factory=dict)

    @classmethod
    def build(
        cls, deps: Mapping[str, Iterable[str]], status: Mapping[str, TaskStatus] | None = None
    ) -> TaskGraph:
        g = cls({k: set(v) for k, v in deps.items()}, dict(status or {}))
        for k in g.deps:
            g.status.setdefault(k, TaskStatus.WAITING)
        unknown = {d for ds in g.deps.values() for d in ds} - set(g.deps)
        if unknown:
            raise ValueError(f"unknown dependencies: {', '.join(sorted(unknown))}")
        return g

    # ---- structure ------------------------------------------------------------------------
    def topo_order(self) -> list[str]:
        """Dependencies first; ties keep insertion order. Raises CycleError with the cycle found."""
        order: list[str] = []
        state: dict[str, int] = {}  # 1 = visiting, 2 = done
        path: list[str] = []

        def visit(n: str) -> None:
            if state.get(n) == 2:
                return
            if state.get(n) == 1:
                raise CycleError([*path[path.index(n) :], n])
            state[n] = 1
            path.append(n)
            for d in sorted(self.deps[n], key=list(self.deps).index):
                visit(d)
            path.pop()
            state[n] = 2
            order.append(n)

        for n in self.deps:
            visit(n)
        return order

    def dependents(self, node: str) -> set[str]:
        return {k for k, ds in self.deps.items() if node in ds}

    def descendants(self, node: str) -> set[str]:
        out: set[str] = set()
        frontier = [node]
        while frontier:
            for d in self.dependents(frontier.pop()):
                if d not in out:
                    out.add(d)
                    frontier.append(d)
        return out

    def sinks(self) -> list[str]:
        """Tasks nothing depends on (the ends of the graph)."""
        depended = {d for ds in self.deps.values() for d in ds}
        return [k for k in self.deps if k not in depended]

    def depth(self) -> int:
        level: dict[str, int] = {}
        for n in self.topo_order():
            level[n] = 1 + max((level[d] for d in self.deps[n]), default=0)
        return max(level.values(), default=0)

    def width(self) -> int:
        """Largest number of tasks at the same depth: how much could run in parallel."""
        level: dict[str, int] = {}
        for n in self.topo_order():
            level[n] = 1 + max((level[d] for d in self.deps[n]), default=0)
        counts: dict[int, int] = {}
        for lv in level.values():
            counts[lv] = counts.get(lv, 0) + 1
        return max(counts.values(), default=0)

    # ---- execution --------------------------------------------------------------------------
    def ready(self) -> list[str]:
        """Waiting/queued tasks whose dependencies are all satisfied, in topological order."""
        return [
            n
            for n in self.topo_order()
            if self.status[n] in (TaskStatus.WAITING, TaskStatus.QUEUED)
            and all(self.status[d] in SATISFIED for d in self.deps[n])
        ]

    def doomed(self) -> list[str]:
        """Waiting tasks that can never start because a dependency failed or was cancelled."""
        return [
            n
            for n in self.topo_order()
            if self.status[n] in (TaskStatus.WAITING, TaskStatus.QUEUED)
            and any(self.status[d] in DEAD for d in self.deps[n])
        ]

    def settled(self) -> bool:
        return all(s.settled for s in self.status.values())

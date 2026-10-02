"""ContextBuilder: decides what an agent is given besides its task, within a token budget, and says why.

Candidates, in priority order:
1. what the caller hands over (for orchestrated tasks: upstream outputs and reviews), which the task needs;
2. the project's pinned facts (pinned project memories);
3. memories recalled for this task, ranked by the retriever (see `app/memory/scoring.py`).

The budget is filled in that order, best score first. When a caller-given block does not fit it is cut
at a sentence boundary rather than dropped; a recalled memory that does not fit is dropped. Everything
is rendered later by the PromptBuilder inside trust fences: memories are data, never instructions.
The `ContextReport` (what was included, cut or dropped, with token counts) is stored with the run.

Files are not pre-loaded: agents read them through tools, so every read is logged and taints the run
when the content is untrusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.agents.prompt import ContextBlock
from app.memory.service import MemoryService
from app.providers.types import estimate_tokens
from app.schemas.agents import AgentDefinition
from app.schemas.memory import ContextEntry, ContextReport, MemoryItemOut

DEFAULT_BUDGET_TOKENS = 12_000
SAFETY = 1.1  # estimates are approximate; keep a margin
FENCE_OVERHEAD = 24  # tokens for the fence tags around each block
MIN_CUT_TOKENS = 200  # a cut block shorter than this is not worth including
RECALL_K = 6
PINNED_K = 5
_SENTENCE_END = re.compile(r"[.!?](?=\s)|\n")


@dataclass(frozen=True)
class ContextRequest:
    agent: AgentDefinition
    project_id: str
    query: str
    objective_id: str | None = None
    given: list[ContextBlock] = field(default_factory=list)
    budget_tokens: int = DEFAULT_BUDGET_TOKENS
    private: bool = False  # a private run may recall memories from other private runs; others may not


@dataclass(frozen=True)
class BuiltContext:
    blocks: list[ContextBlock]
    report: ContextReport
    taint: list[str]  # recalled memories that were written by runs which had read untrusted content


@dataclass
class _Segment:
    block: ContextBlock
    kind: Literal["upstream", "memory", "given"]
    priority: int
    score: float
    why: str
    memory: MemoryItemOut | None = None


def cost(text: str) -> int:
    return int(estimate_tokens(text) * SAFETY) + FENCE_OVERHEAD


def cut_to(text: str, tokens: int) -> str:
    """Shorten ``text`` to about ``tokens``, ending at a sentence boundary when there is one nearby."""
    chars = max(0, int((tokens - FENCE_OVERHEAD) / SAFETY * 3.5) - 40)
    if len(text) <= chars:
        return text
    head = text[:chars]
    ends = [m.end() for m in _SENTENCE_END.finditer(head)]
    if ends and ends[-1] > chars * 0.6:
        head = head[: ends[-1]]
    omitted = len(text) - len(head)
    return head.rstrip() + f"\n…[{omitted:,} characters omitted to fit the context]"


def memory_block(item: MemoryItemOut, why: str) -> ContextBlock:
    origin = item.source.kind if item.source.kind != "agent" else f"agent {item.source.agent or ''}".strip()
    flags = ", written after reading untrusted content" if item.source.tainted else ""
    head = f"Remembered ({item.scope} memory from {origin}{flags}; {why}):"
    return ContextBlock(f"memory:{item.id}", f"{head}\n{item.content}")


class ContextBuilder:
    def __init__(
        self, memory: MemoryService | None, *, recall_k: int = RECALL_K, pinned_k: int = PINNED_K
    ) -> None:
        self._memory = memory
        self._recall_k = recall_k
        self._pinned_k = pinned_k

    async def build(self, req: ContextRequest) -> BuiltContext:
        segments: list[_Segment] = []
        for b in req.given:
            kind: Literal["upstream", "given"] = "upstream" if b.source.startswith("task:") else "given"
            why = "output of an earlier task" if kind == "upstream" else "provided with the task"
            segments.append(_Segment(b, kind, 0, 1.0, why))

        notes: list[str] = []
        readable = [s for s in req.agent.memory_scope.read if s in ("project", "global")]
        if self._memory is not None and readable:
            seen: set[str] = set()
            if "project" in readable:
                for item in await self._memory.pinned(
                    req.project_id, limit=self._pinned_k, include_private=req.private
                ):
                    seen.add(item.id)
                    segments.append(
                        _Segment(
                            memory_block(item, "a pinned project fact"),
                            "memory",
                            1,
                            1.0,
                            "pinned project fact",
                            item,
                        )
                    )
            hits = await self._memory.search(
                req.query,
                scopes=readable,
                project_id=req.project_id,
                k=self._recall_k,
                objective_id=req.objective_id,
                include_private=req.private,
            )
            for h in hits:
                if h.item.id in seen:
                    continue
                why = f"relevant to this task (score {h.score.total:.2f})"
                segments.append(_Segment(memory_block(h.item, why), "memory", 2, h.score.total, why, h.item))
        elif self._memory is not None:
            notes.append("This agent does not read memory.")

        segments.sort(key=lambda s: (s.priority, -s.score))
        left = req.budget_tokens
        blocks: list[ContextBlock] = []
        entries: list[ContextEntry] = []
        taint: list[str] = []
        for seg in segments:
            need = cost(seg.block.text)
            entry = dict(
                source=seg.block.source,
                kind=seg.kind,
                score=round(seg.score, 4),
                memory_id=seg.memory.id if seg.memory else None,
            )
            if need <= left:
                blocks.append(seg.block)
                left -= need
                entries.append(ContextEntry(**entry, tokens=need, included=True, reason=seg.why))
            elif seg.kind != "memory" and left >= MIN_CUT_TOKENS:
                text = cut_to(seg.block.text, left)
                used = cost(text)
                blocks.append(ContextBlock(seg.block.source, text))
                left -= used
                entries.append(
                    ContextEntry(
                        **entry,
                        tokens=used,
                        included=True,
                        truncated=True,
                        reason=f"{seg.why}; shortened to fit",
                    )
                )
            else:
                entries.append(
                    ContextEntry(**entry, tokens=need, included=False, reason="over the context budget")
                )
                continue
            if seg.memory is not None and seg.memory.source.tainted:
                taint.append(f"memory:{seg.memory.id}")

        report = ContextReport(
            budget_tokens=req.budget_tokens,
            used_tokens=req.budget_tokens - left,
            entries=entries,
            memory_query=req.query[:300] if readable else "",
            notes=notes,
        )
        return BuiltContext(blocks, report, taint)

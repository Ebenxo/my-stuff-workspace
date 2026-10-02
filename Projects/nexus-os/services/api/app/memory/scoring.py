"""Retrieval scoring. Pure: candidates and a query in, ranked hits with a visible breakdown out.

    score = .45·semantic + .15·keyword + .15·recency + .15·importance + .10·task

- semantic: cosine similarity between the query's and the item's vectors;
- keyword: BM25 over the candidate set, divided by the best score in the set (0 to 1);
- recency: exp(-age/τ), age since the item was last used or changed (τ 30 days for project memory,
  180 for global, 7 for conversation);
- importance: 0 to 1, set by the source (see `importance_for`); pinned items are 1;
- task: 1 when the item came from the same objective, 0.5 when its tags name words in the query.

An item must also be *about* the query (semantic ≥ MIN_SEMANTIC or any keyword match) to be returned:
importance and recency rank relevant items, they never make an unrelated item relevant.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.memory.embedder import cosine, words
from app.schemas.memory import MemoryItemOut, ScoreBreakdown

WEIGHTS = {"semantic": 0.45, "keyword": 0.15, "recency": 0.15, "importance": 0.15, "task": 0.10}
TAU_DAYS = {"project": 30.0, "global": 180.0, "conversation": 7.0}
MIN_SEMANTIC = 0.12
K1, B = 1.2, 0.75

# Importance by source, and how far a proposer may move it (an agent cannot self-promote its memories).
BANDS = {"user": 0.8, "agent": 0.5, "objective": 0.4, "summary": 0.4}
BAND_WIDTH = 0.2
TAINTED_CAP = 0.4


def importance_for(kind: str, requested: float | None = None, *, tainted: bool = False) -> float:
    base = BANDS.get(kind, 0.5)
    value = base if requested is None else min(max(requested, base - BAND_WIDTH), base + BAND_WIDTH)
    if tainted:
        value = min(value, TAINTED_CAP)
    return round(min(max(value, 0.0), 1.0), 3)


@dataclass(frozen=True)
class Scored:
    item: MemoryItemOut
    score: ScoreBreakdown


def bm25(query: Sequence[str], docs: Sequence[Sequence[str]]) -> list[float]:
    """Okapi BM25 of each doc for the query terms, over this set of docs."""
    n = len(docs)
    if not n or not query:
        return [0.0] * n
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    terms = set(query)
    out = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in terms:
            if not tf[t]:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * len(d) / avgdl))
        out.append(s)
    return out


def recency(item: MemoryItemOut, now: datetime) -> float:
    ref = item.last_accessed_at or item.updated_at
    age_days = max(0.0, (now - ref).total_seconds() / 86_400)
    return math.exp(-age_days / TAU_DAYS.get(item.scope, 30.0))


def rank(
    query: str,
    query_vector: list[float],
    candidates: Sequence[tuple[MemoryItemOut, list[float] | None]],
    *,
    now: datetime,
    objective_id: str | None = None,
    k: int = 8,
) -> list[Scored]:
    q_words = words(query)
    docs = [words(item.content + " " + " ".join(item.tags)) for item, _ in candidates]
    raw_kw = bm25(q_words, docs)
    best_kw = max(raw_kw, default=0.0) or 1.0
    q_terms = set(q_words)
    scored = []
    for (item, vec), kw_raw in zip(candidates, raw_kw, strict=True):
        sem = max(0.0, cosine(query_vector, vec))
        kw = kw_raw / best_kw
        if sem < MIN_SEMANTIC and kw_raw <= 0:
            continue
        task = 0.0
        if objective_id and item.source.objective_id == objective_id:
            task = 1.0
        elif q_terms & {w for tag in item.tags for w in words(tag)}:
            task = 0.5
        parts = {
            "semantic": sem,
            "keyword": kw,
            "recency": recency(item, now),
            "importance": item.importance,
            "task": task,
        }
        total = sum(WEIGHTS[name] * value for name, value in parts.items())
        scored.append(
            Scored(item, ScoreBreakdown(**{n: round(v, 4) for n, v in parts.items()}, total=round(total, 4)))
        )
    scored.sort(key=lambda s: (-s.score.total, s.item.id))
    return scored[:k]

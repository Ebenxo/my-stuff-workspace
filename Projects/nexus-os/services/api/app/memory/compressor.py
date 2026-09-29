"""Memory compression: fold old, low-value notes that belong together into one summary.

Pure and deterministic, so it needs no model and gives the same result every time. Groups form from
items similar to any member (cosine ≥ GROUP_SIMILARITY) or sharing a tag; only groups of MIN_GROUP or more
are compressed. The summary keeps the group's most central sentences in their original order. The
service soft-deletes the originals only after the summary exists, and can restore them.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.memory.embedder import cosine, words
from app.schemas.memory import MemoryItemOut

GROUP_SIMILARITY = 0.28  # related notes score ~0.3 to 0.4 with the hashing embedder; unrelated < 0.2
MIN_GROUP = 3
MAX_GROUP = 12
SUMMARY_CHARS = 700
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Group:
    items: list[MemoryItemOut]

    @property
    def tags(self) -> list[str]:
        seen: dict[str, None] = {}
        for i in self.items:
            for t in i.tags:
                seen.setdefault(t, None)
        return list(seen)[:12]


def group(candidates: Sequence[tuple[MemoryItemOut, list[float] | None]]) -> list[Group]:
    """Greedy single-pass grouping in creation order: each item joins the first group it fits."""
    groups: list[list[tuple[MemoryItemOut, list[float] | None]]] = []
    for item, vec in candidates:
        for g in groups:
            if len(g) >= MAX_GROUP:
                continue
            if any(cosine(vec, v) >= GROUP_SIMILARITY or set(item.tags) & set(i.tags) for i, v in g):
                g.append((item, vec))
                break
        else:
            groups.append([(item, vec)])
    return [Group([i for i, _ in g]) for g in groups if len(g) >= MIN_GROUP]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if len(s.strip()) > 2]


def summarise(g: Group, limit: int = SUMMARY_CHARS) -> str:
    """The group's most representative sentences (by shared vocabulary), in their original order."""
    all_sentences = [(n, s) for n, item in enumerate(g.items) for s in sentences(item.content)]
    vocab: Counter[str] = Counter()
    for item in g.items:
        vocab.update(set(words(item.content)))
    ranked = sorted(
        range(len(all_sentences)),
        key=lambda i: (
            -sum(vocab[w] for w in set(words(all_sentences[i][1])))
            / (1 + len(words(all_sentences[i][1])) ** 0.5)
        ),
    )
    chosen: list[int] = []
    used = 0
    seen: set[str] = set()
    for i in ranked:
        text = all_sentences[i][1]
        key = text.lower()
        if key in seen or used + len(text) > limit:
            continue
        chosen.append(i)
        seen.add(key)
        used += len(text) + 1
    body = " ".join(all_sentences[i][1] for i in sorted(chosen))
    return f"Summary of {len(g.items)} older notes: {body}"

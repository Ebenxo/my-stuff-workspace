"""Embedders turn text into vectors for semantic recall.

The default, `HashingEmbedder`, is deterministic, local and dependency-free: signed feature hashing over
normalised words, word pairs and character trigrams. It needs no download and no network and works
offline. It is *lexical*: "car" and "automobile" are not close, but "invoice", "invoices" and
"invoicing" are. A neural embedder (Ollama, OpenAI-compatible, Gemini) can implement `Embedder`; each
stored vector records which embedder produced it, and stale vectors are re-embedded in the background.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from itertools import pairwise
from typing import Protocol

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

# A word list reads better as text than as a 70-line literal.
STOPWORDS = frozenset(
    """
    a an and are as at be been but by can did do does for from had has have he her his i if in into
    is it its me my no not of on or our she so than that the their them then there these they this
    to too up us was we were what when where which who will with would you your
    """.split()  # noqa: SIM905
)


def words(text: str) -> list[str]:
    """Lower-cased words with stopwords removed and a light plural/verb-ending fold."""
    out = []
    for w in _WORD.findall(text.lower()):
        if w in STOPWORDS or len(w) < 2:
            continue
        out.append(_fold(w))
    return out


def _fold(w: str) -> str:
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    WORD_WEIGHT = 1.0
    PAIR_WEIGHT = 0.6
    TRIGRAM_WEIGHT = 0.35

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def name(self) -> str:
        return f"hashing-v1-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def _slot(self, feature: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        return h % self._dim, (1.0 if (h >> 63) & 1 else -1.0)

    def embed(self, text: str) -> list[float]:
        ws = words(text)
        feats: Counter[str] = Counter()
        for w in ws:
            feats["w:" + w] += 1
            padded = f"^{w}$"
            for i in range(len(padded) - 2):
                feats["c:" + padded[i : i + 3]] += 1
        for a, b in pairwise(ws):
            feats[f"p:{a} {b}"] += 1
        vec = [0.0] * self._dim
        for feat, count in feats.items():
            weight = {"w": self.WORD_WEIGHT, "p": self.PAIR_WEIGHT, "c": self.TRIGRAM_WEIGHT}[feat[0]]
            slot, sign = self._slot(feat)
            vec[slot] += sign * weight * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vec))
        return [round(v / norm, 6) for v in vec] if norm else vec


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

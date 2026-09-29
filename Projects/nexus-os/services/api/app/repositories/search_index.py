"""The universal search index: one row per searchable thing (project, objective, artifact, memory).

`search_index` is an FTS5 virtual table (migration 0004), ranked with bm25 and title matches weighted
above body matches. If the SQLite build had no FTS5 the migration made a plain table instead, and
queries fall back to LIKE on every term.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text

from app.models.database import Database

_WORD = re.compile(r"\w+", re.UNICODE)
MAX_BODY_CHARS = 20_000


@dataclass(frozen=True)
class IndexHit:
    kind: str
    ref_id: str
    project_id: str | None
    title: str
    snippet: str
    score: float  # higher is better


def fts_query(q: str) -> str | None:
    """Turn free text into a safe FTS5 expression: every word must appear (prefix match on the last).

    Words are quoted, so FTS5 syntax typed by a person (or pasted from anywhere) is always literal.
    """
    words = _WORD.findall(q)[:12]
    if not words:
        return None
    quoted = [f'"{w}"' for w in words]
    quoted[-1] += "*"
    return " AND ".join(quoted)


class SearchIndex:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._fts: bool | None = None

    async def uses_fts(self) -> bool:
        if self._fts is None:
            async with self._db.session() as s:
                sql = (
                    await s.execute(text("SELECT sql FROM sqlite_master WHERE name = 'search_index'"))
                ).scalar_one_or_none()
            self._fts = bool(sql and "fts5" in sql.lower())
        return self._fts

    async def upsert(self, kind: str, ref_id: str, project_id: str | None, title: str, body: str) -> None:
        async with self._db.session() as s:
            await s.execute(
                text("DELETE FROM search_index WHERE kind = :k AND ref_id = :r"), {"k": kind, "r": ref_id}
            )
            await s.execute(
                text(
                    "INSERT INTO search_index (kind, ref_id, project_id, title, body) "
                    "VALUES (:k, :r, :p, :t, :b)"
                ),
                {"k": kind, "r": ref_id, "p": project_id, "t": title[:500], "b": body[:MAX_BODY_CHARS]},
            )

    async def delete(self, kind: str, ref_id: str) -> None:
        async with self._db.session() as s:
            await s.execute(
                text("DELETE FROM search_index WHERE kind = :k AND ref_id = :r"), {"k": kind, "r": ref_id}
            )

    async def count(self) -> int:
        async with self._db.session() as s:
            return int((await s.execute(text("SELECT count(*) FROM search_index"))).scalar_one())

    async def clear(self) -> None:
        async with self._db.session() as s:
            await s.execute(text("DELETE FROM search_index"))

    async def query(
        self, q: str, *, kinds: Sequence[str] = (), project_id: str | None = None, limit: int = 30
    ) -> list[IndexHit]:
        if await self.uses_fts():
            return await self._query_fts(q, kinds, project_id, limit)
        return await self._query_like(q, kinds, project_id, limit)

    async def _query_fts(
        self, q: str, kinds: Sequence[str], project_id: str | None, limit: int
    ) -> list[IndexHit]:
        expr = fts_query(q)
        if expr is None:
            return []
        where, params = _filters(kinds, project_id)
        # Only fixed fragments and named placeholders are joined here; every value is a bound parameter.
        sql = (
            "SELECT kind, ref_id, project_id, title, "  # noqa: S608
            "snippet(search_index, 4, '[', ']', ' … ', 12) AS snip, "
            "bm25(search_index, 0, 0, 0, 5.0, 1.0) AS rank "
            f"FROM search_index WHERE search_index MATCH :q{where} ORDER BY rank LIMIT :limit"
        )
        async with self._db.session() as s:
            rows = (await s.execute(text(sql), {"q": expr, "limit": limit, **params})).all()
        # bm25 is negative and lower is better; flip it so callers can sort descending.
        return [IndexHit(k, r, p, t, sn or "", round(-float(rank), 4)) for k, r, p, t, sn, rank in rows]

    async def _query_like(
        self, q: str, kinds: Sequence[str], project_id: str | None, limit: int
    ) -> list[IndexHit]:
        words = [w.lower() for w in _WORD.findall(q)[:12]]
        if not words:
            return []
        where, params = _filters(kinds, project_id)
        for i, w in enumerate(words):
            where += f" AND (lower(title) LIKE :w{i} ESCAPE '\\' OR lower(body) LIKE :w{i} ESCAPE '\\')"
            params[f"w{i}"] = "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql = f"SELECT kind, ref_id, project_id, title, body FROM search_index WHERE 1=1{where} LIMIT :limit"  # noqa: S608
        async with self._db.session() as s:
            rows = (await s.execute(text(sql), {"limit": limit, **params})).all()
        hits = []
        for k, r, p, t, body in rows:
            score = sum(3.0 * t.lower().count(w) + body.lower().count(w) for w in words)
            hits.append(IndexHit(k, r, p, t, _like_snippet(body, words[0]), float(score)))
        return sorted(hits, key=lambda h: -h.score)


def _filters(kinds: Sequence[str], project_id: str | None) -> tuple[str, dict[str, object]]:
    where = ""
    params: dict[str, object] = {}
    if kinds:
        names = [f":kind{i}" for i in range(len(kinds))]
        where += f" AND kind IN ({', '.join(names)})"
        params.update({f"kind{i}": k for i, k in enumerate(kinds)})
    if project_id:
        where += " AND (project_id = :project OR project_id IS NULL)"
        params["project"] = project_id
    return where, params


def _like_snippet(body: str, word: str, width: int = 120) -> str:
    i = body.lower().find(word)
    if i < 0:
        return body[:width]
    start = max(0, i - width // 3)
    return ("… " if start else "") + body[start : start + width] + (" …" if start + width < len(body) else "")

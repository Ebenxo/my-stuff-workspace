"""EventBus: persist every event to the hash-chained audit log, then fan out in-process."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from app.core.clock import Clock, SystemClock
from app.core.ids import new_id
from app.core.security import redact
from app.events.types import EventType
from app.models.database import Database
from app.models.foundation import Event
from app.repositories.events import EventFilter, EventRepository, to_record
from app.schemas.events import ChainVerification, EventRecord

log = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64


class _AllChains:
    def __repr__(self) -> str:
        return "ALL_CHAINS"


ALL_CHAINS = _AllChains()
Listener = Callable[[EventRecord], Awaitable[None] | None]


def to_jsonable(obj: Any) -> Any:
    """Reduce arbitrary values to plain JSON types: str keys, lists, ISO datetimes, str() fallback."""
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, datetime):
        return obj.astimezone(UTC).isoformat(timespec="microseconds") if obj.tzinfo else obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [to_jsonable(v) for v in obj]
    return str(obj)


def canonical_json(obj: Any) -> str:
    return json.dumps(
        to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def compute_hash(
    prev_hash: str,
    *,
    id: str,
    ts: datetime,
    type: str,
    project_id: str | None,
    objective_id: str | None,
    task_id: str | None,
    run_id: str | None,
    agent_id: str | None,
    actor: str,
    payload: dict[str, Any],
) -> str:
    body = canonical_json(
        {
            "id": id,
            "ts": ts.astimezone(UTC).isoformat(timespec="microseconds"),
            "type": type,
            "project_id": project_id,
            "objective_id": objective_id,
            "task_id": task_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "actor": actor,
            "payload": payload,
        }
    )
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


class Subscription:
    """A bounded live feed. If the consumer falls behind it is flagged and must resync via replay."""

    def __init__(self, flt: EventFilter, maxsize: int) -> None:
        self.filter = flt
        self.queue: asyncio.Queue[EventRecord] = asyncio.Queue(maxsize=maxsize)
        self.overflowed = False

    def offer(self, record: EventRecord) -> None:
        if not self.filter.matches(record):
            return
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            self.overflowed = True


class EventBus:
    def __init__(
        self, db: Database, clock: Clock | None = None, *, subscriber_queue_size: int = 1000
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._lock = asyncio.Lock()
        self._subscribers: set[Subscription] = set()
        self._listeners: list[Listener] = []
        self._last_hash: dict[str | None, str] = {}
        self._queue_size = subscriber_queue_size

    def add_listener(self, listener: Listener) -> None:
        """In-process reaction hook (e.g. notifications). Listener errors are logged, never raised."""
        self._listeners.append(listener)

    async def emit(
        self,
        type: EventType | str,
        *,
        project_id: str | None = None,
        objective_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        actor: str = "system",
        payload: dict[str, Any] | None = None,
    ) -> EventRecord:
        # Normalise through JSON so the hashed payload equals what the database round-trips.
        clean_payload: dict[str, Any] = json.loads(canonical_json(redact(payload or {})))
        type_str = type.value if isinstance(type, EventType) else str(type)
        async with self._lock:
            event_id = new_id("evt")
            ts = self._clock.now()
            async with self._db.session() as session:
                repo = EventRepository(session)
                prev = self._last_hash.get(project_id)
                if prev is None:
                    prev = await repo.last_hash(project_id) or GENESIS_HASH
                digest = compute_hash(
                    prev,
                    id=event_id,
                    ts=ts,
                    type=type_str,
                    project_id=project_id,
                    objective_id=objective_id,
                    task_id=task_id,
                    run_id=run_id,
                    agent_id=agent_id,
                    actor=actor,
                    payload=clean_payload,
                )
                row = await repo.insert(
                    Event(
                        id=event_id,
                        ts=ts,
                        type=type_str,
                        project_id=project_id,
                        objective_id=objective_id,
                        task_id=task_id,
                        run_id=run_id,
                        agent_id=agent_id,
                        actor=actor,
                        payload=clean_payload,
                        prev_hash=prev,
                        hash=digest,
                    )
                )
                record = to_record(row)
            self._last_hash[project_id] = digest
        self._fan_out(record)
        await self._notify_listeners(record)
        return record

    def _fan_out(self, record: EventRecord) -> None:
        for sub in list(self._subscribers):
            sub.offer(record)

    async def _notify_listeners(self, record: EventRecord) -> None:
        for listener in self._listeners:
            try:
                result = listener(record)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception("event listener failed for %s", record.type)

    @contextmanager
    def subscribe(self, flt: EventFilter | None = None) -> Iterator[Subscription]:
        sub = Subscription(flt or EventFilter(), self._queue_size)
        self._subscribers.add(sub)
        try:
            yield sub
        finally:
            self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def query(
        self,
        flt: EventFilter,
        *,
        after_seq: int = 0,
        before_seq: int = 0,
        limit: int = 200,
        newest_first: bool = False,
    ) -> list[EventRecord]:
        async with self._db.session() as session:
            return await EventRepository(session).query(
                flt, after_seq=after_seq, before_seq=before_seq, limit=limit, newest_first=newest_first
            )

    async def latest_seq(self) -> int:
        async with self._db.session() as session:
            return await EventRepository(session).latest_seq()

    async def replay(
        self, flt: EventFilter, after_seq: int, page_size: int = 500
    ) -> AsyncIterator[EventRecord]:
        cursor = after_seq
        while True:
            page = await self.query(flt, after_seq=cursor, limit=page_size)
            if not page:
                return
            for record in page:
                yield record
            cursor = page[-1].seq

    async def verify(self, project_id: str | _AllChains | None = ALL_CHAINS) -> ChainVerification:
        """Recompute hash chains. ``ALL_CHAINS`` verifies every chain; ``None`` only the global one."""
        async with self._db.session() as session:
            repo = EventRepository(session)
            chains: list[str | None] = (
                list(await repo.chain_ids()) if isinstance(project_id, _AllChains) else [project_id]
            )
            checked = 0
            for chain in chains:
                prev = GENESIS_HASH
                cursor = 0
                while True:
                    rows = await repo.chain(chain, after_seq=cursor, limit=1000)
                    if not rows:
                        break
                    for row in rows:
                        expected = compute_hash(
                            prev,
                            id=row.id,
                            ts=row.ts,
                            type=row.type,
                            project_id=row.project_id,
                            objective_id=row.objective_id,
                            task_id=row.task_id,
                            run_id=row.run_id,
                            agent_id=row.agent_id,
                            actor=row.actor,
                            payload=row.payload,
                        )
                        if row.prev_hash != prev or row.hash != expected:
                            return ChainVerification(
                                ok=False,
                                chains_checked=len(chains),
                                events_checked=checked,
                                first_bad_seq=row.seq,
                                detail="hash chain broken at this event",
                            )
                        prev = row.hash
                        checked += 1
                        cursor = row.seq
            return ChainVerification(ok=True, chains_checked=len(chains), events_checked=checked)

    async def close(self) -> None:
        self._subscribers.clear()
        with contextlib.suppress(Exception):
            self._listeners.clear()

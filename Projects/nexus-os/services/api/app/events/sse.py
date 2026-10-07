"""Server-Sent Events over the EventBus with gap-free replay from ``Last-Event-ID``."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from app.events.bus import EventBus
from app.repositories.events import EventFilter
from app.schemas.events import EventRecord

RETRY_MS = 3000


def format_sse(record: EventRecord) -> str:
    data = json.dumps(record.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False)
    return f"id: {record.seq}\nevent: {record.type}\ndata: {data}\n\n"


async def event_stream(
    bus: EventBus,
    flt: EventFilter,
    *,
    after_seq: int | None = None,
    heartbeat_s: float = 15.0,
) -> AsyncIterator[str]:
    """Yield SSE frames.

    ``after_seq=None`` starts at "now". A number replays everything newer first, then tails live
    events. The subscription is opened *before* replay so nothing committed in between is lost;
    duplicates are dropped by sequence number.
    """
    yield f"retry: {RETRY_MS}\n\n"
    with bus.subscribe(flt) as sub:
        last = after_seq if after_seq is not None else await bus.latest_seq()
        if after_seq is not None:
            async for record in bus.replay(flt, after_seq):
                last = max(last, record.seq)
                yield format_sse(record)
        while True:
            if sub.overflowed:
                yield f"event: resync\ndata: {json.dumps({'after': last})}\n\n"
                return
            try:
                record = await asyncio.wait_for(sub.queue.get(), timeout=heartbeat_s)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if record.seq <= last:
                continue
            last = record.seq
            yield format_sse(record)

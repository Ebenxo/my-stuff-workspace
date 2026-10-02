"""Background job queue. In-process asyncio today; the interface fits Redis/Celery later."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.core.ids import new_id

log = logging.getLogger(__name__)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobInfo:
    id: str
    name: str
    key: str | None
    status: JobStatus = JobStatus.PENDING
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class QueueStats:
    pending: int
    running: int
    completed: int
    failed: int
    cancelled: int
    concurrency: int


JobFn = Callable[[], Awaitable[Any]]
ErrorHook = Callable[[JobInfo, BaseException], Awaitable[None]]


class JobQueue(Protocol):
    async def submit(self, name: str, fn: JobFn, *, key: str | None = None) -> str: ...
    def cancel(self, job_id: str) -> bool: ...
    def cancel_key(self, key: str) -> int: ...
    def stats(self) -> QueueStats: ...
    def get(self, job_id: str) -> JobInfo | None: ...
    async def join(self, *, timeout_s: float | None = None) -> None: ...
    async def shutdown(self) -> None: ...


class InProcessJobQueue:
    def __init__(
        self, concurrency: int = 4, *, history: int = 200, on_error: ErrorHook | None = None
    ) -> None:
        self._concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._info: dict[str, JobInfo] = {}
        self._finished: deque[str] = deque(maxlen=history)
        self._counts = {s: 0 for s in JobStatus}
        self._on_error = on_error
        self._closed = False

    async def submit(self, name: str, fn: JobFn, *, key: str | None = None) -> str:
        if self._closed:
            raise RuntimeError("job queue is shut down")
        info = JobInfo(id=new_id("job"), name=name, key=key)
        self._info[info.id] = info
        self._tasks[info.id] = asyncio.create_task(self._run(info, fn), name=f"job:{name}:{info.id}")
        return info.id

    async def _run(self, info: JobInfo, fn: JobFn) -> None:
        try:
            async with self._sem:
                info.status = JobStatus.RUNNING
                info.started_at = datetime.now(UTC)
                await fn()
            info.status = JobStatus.COMPLETED
        except asyncio.CancelledError:
            info.status = JobStatus.CANCELLED
        except Exception as exc:
            info.status = JobStatus.FAILED
            info.error = f"{type(exc).__name__}: {exc}"
            log.exception("job %s (%s) failed", info.id, info.name)
            if self._on_error:
                try:
                    await self._on_error(info, exc)
                except Exception:
                    log.exception("job error hook failed")
        finally:
            info.finished_at = datetime.now(UTC)
            self._counts[info.status] += 1
            self._tasks.pop(info.id, None)
            self._finished.append(info.id)
            self._trim()

    def _trim(self) -> None:
        keep = set(self._finished) | set(self._tasks)
        for job_id in [j for j in self._info if j not in keep]:
            del self._info[job_id]

    def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def cancel_key(self, key: str) -> int:
        n = 0
        for job_id, info in list(self._info.items()):
            if info.key == key and self.cancel(job_id):
                n += 1
        return n

    def get(self, job_id: str) -> JobInfo | None:
        return self._info.get(job_id)

    def stats(self) -> QueueStats:
        pending = sum(1 for i in self._info.values() if i.status is JobStatus.PENDING)
        running = sum(1 for i in self._info.values() if i.status is JobStatus.RUNNING)
        return QueueStats(
            pending=pending,
            running=running,
            completed=self._counts[JobStatus.COMPLETED],
            failed=self._counts[JobStatus.FAILED],
            cancelled=self._counts[JobStatus.CANCELLED],
            concurrency=self._concurrency,
        )

    async def join(self, *, timeout_s: float | None = None) -> None:
        pending = [t for t in self._tasks.values() if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout_s)

    async def shutdown(self) -> None:
        self._closed = True
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

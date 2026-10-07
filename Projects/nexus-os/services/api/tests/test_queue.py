from __future__ import annotations

import asyncio

from app.tasks.queue import InProcessJobQueue, JobStatus


async def test_jobs_run_and_are_counted() -> None:
    q = InProcessJobQueue(concurrency=2)
    results: list[int] = []

    async def job(i: int) -> None:
        results.append(i)

    ids = [await q.submit(f"j{i}", lambda i=i: job(i)) for i in range(5)]  # type: ignore[misc]
    await q.join(timeout_s=2)
    assert sorted(results) == list(range(5))
    assert q.stats().completed == 5
    assert q.get(ids[0]).status is JobStatus.COMPLETED  # type: ignore[union-attr]
    await q.shutdown()


async def test_concurrency_is_bounded() -> None:
    q = InProcessJobQueue(concurrency=2)
    running = 0
    peak = 0

    async def job() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1

    for i in range(8):
        await q.submit(f"j{i}", job)
    await q.join(timeout_s=3)
    assert peak == 2
    await q.shutdown()


async def test_failure_is_recorded_and_hooked() -> None:
    seen: list[str] = []

    async def hook(info, exc) -> None:  # type: ignore[no-untyped-def]
        seen.append(str(exc))

    q = InProcessJobQueue(on_error=hook)

    async def boom() -> None:
        raise ValueError("nope")

    job_id = await q.submit("boom", boom)
    await q.join(timeout_s=2)
    info = q.get(job_id)
    assert info is not None
    assert info.status is JobStatus.FAILED
    assert info.error == "ValueError: nope"
    assert seen == ["nope"]
    assert q.stats().failed == 1
    await q.shutdown()


async def test_cancel_by_id_and_key() -> None:
    q = InProcessJobQueue(concurrency=1)
    gate = asyncio.Event()

    async def wait() -> None:
        await gate.wait()

    a = await q.submit("a", wait, key="obj_1")
    await q.submit("b", wait, key="obj_1")
    await q.submit("c", wait, key="obj_2")
    await asyncio.sleep(0.01)
    assert q.cancel(a)
    assert q.cancel_key("obj_1") >= 1
    gate.set()
    await q.join(timeout_s=2)
    assert q.stats().cancelled >= 2
    assert not q.cancel("job_missing")
    await q.shutdown()


async def test_shutdown_cancels_and_rejects_new_work() -> None:
    q = InProcessJobQueue()
    gate = asyncio.Event()

    async def wait() -> None:
        await gate.wait()

    await q.submit("w", wait)
    await q.shutdown()
    try:
        await q.submit("late", wait)
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("submit after shutdown must fail")

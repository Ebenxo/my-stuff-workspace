from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.core.instance_lock import InstanceLock, InstanceLockedError
from app.core.secrets import MemorySecretStore
from app.core.settings import Settings
from app.main import create_app
from app.schemas.runtime import RunStatus
from tests.agent_helpers import make_ae


def test_only_one_holder_at_a_time(tmp_path: Path) -> None:
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    first.acquire()
    assert first.held and first.path.read_text().strip().isdigit()  # the owner's pid, for diagnosis
    with pytest.raises(InstanceLockedError, match="already using"):
        second.acquire()
    assert not second.held
    first.release()
    second.acquire()  # released locks can be taken again
    assert second.held
    second.release()
    second.release()  # releasing twice is harmless


async def test_a_second_api_on_the_same_home_cannot_disturb_the_first(
    app: FastAPI, settings: Settings
) -> None:
    # Found live: a second dev server on the same folder ran startup recovery, marking the first
    # server's live runs "interrupted", and only then failed to bind its port.
    ae = await make_ae(app)
    run = await ae.c.runner.create(ae.request(ae.agent(tools=[])))  # a run the first instance owns
    second = create_app(settings, secrets=MemorySecretStore())
    with pytest.raises(InstanceLockedError):
        async with second.router.lifespan_context(second):
            pass
    assert (await ae.c.run_store.get(run.id)).status is RunStatus.RUNNING
    assert not hasattr(second.state, "container")


async def test_the_lock_is_released_when_the_app_stops(settings: Settings) -> None:
    for _ in range(2):  # a clean restart on the same folder works
        a = create_app(settings, secrets=MemorySecretStore())
        async with a.router.lifespan_context(a):
            assert InstanceLock(settings.home).path.exists()

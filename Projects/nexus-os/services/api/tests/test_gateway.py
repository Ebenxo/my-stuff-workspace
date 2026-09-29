from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.core.failures import FailureCategory
from app.providers.errors import (
    ProviderAuthError,
    ProviderRateLimited,
    ProviderRefusal,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.gateway import CallContext, GatewayError, LLMGateway
from app.providers.scripted import ScriptedProvider
from app.providers.types import ChatMessage, GenerateRequest
from app.repositories.events import EventFilter
from app.schemas.providers import ProviderCreate
from tests.conftest import Upstream
from tests.providers_helpers import Answer

GOOD = Answer(city="Paris", population_millions=2.1)


def req() -> GenerateRequest:
    return GenerateRequest(model="ignored", messages=[ChatMessage(role="user", content="hello there")])


@pytest.fixture
async def env(app: FastAPI):  # type: ignore[no-untyped-def]
    c = app.state.container
    scripted: dict[str, ScriptedProvider] = {}
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    c.registry._demo_factory = lambda pid: scripted.setdefault(pid, ScriptedProvider(pid))
    c.router.auto_route_demo = True
    gateway = LLMGateway(c.registry, c.router, c.usage, c.bus, sleep=fake_sleep, jitter=lambda: 0.0)

    async def add(name: str = "Demo") -> tuple[str, ScriptedProvider]:
        p = await c.providers.create(ProviderCreate(kind="demo", name=name, default_model="demo:scripted"))
        scripted.setdefault(p.id, ScriptedProvider(p.id))
        return p.id, scripted[p.id]

    return SimpleNamespace(c=c, gateway=gateway, add=add, sleeps=sleeps, scripted=scripted)


async def usage_rows(env) -> list:  # type: ignore[no-untyped-def]
    return (await env.c.usage.summary(days=1, group_by="model")).groups


async def test_success_records_usage_and_reports_route(env) -> None:  # type: ignore[no-untyped-def]
    pid, p = await env.add()
    p.push("hello back")
    result, meta = await env.gateway.generate(CallContext(agent_id="agent_a", project_id="proj_1"), req())
    assert result.text == "hello back"
    assert (
        meta.provider_id == pid
        and meta.model == "demo:scripted"
        and not meta.fallback_used
        and meta.retries == 0
    )
    assert p.requests[0].model == "demo:scripted"  # the routed model is what the adapter receives
    s = await env.c.usage.summary(days=1, group_by="agent")
    assert s.groups[0].key == "agent_a" and s.groups[0].calls == 1
    assert s.groups[0].unknown_cost_calls == 0  # local demo is known-free


async def test_retryable_error_retries_with_backoff_and_honours_retry_after(env) -> None:  # type: ignore[no-untyped-def]
    _, p = await env.add()
    p.push(ProviderRateLimited("slow down", retry_after=7), ProviderUnavailable("blip"), "finally")
    result, meta = await env.gateway.generate(CallContext(), req())
    assert result.text == "finally" and meta.retries == 2
    assert env.sleeps[0] == pytest.approx(7.0)  # Retry-After beats the computed backoff
    assert env.sleeps[1] == pytest.approx(2.0)  # exponential: base 1s * 2^1


async def test_backoff_is_capped(env) -> None:  # type: ignore[no-untyped-def]
    _, p = await env.add()
    p.push(*[ProviderRateLimited("x", retry_after=9999)] * 2, "ok")
    await env.gateway.generate(CallContext(max_retries=3), req())
    assert max(env.sleeps) <= 30.0


async def test_exhausted_retries_fall_back_to_the_next_model_and_say_so(env) -> None:  # type: ignore[no-untyped-def]
    a, pa = await env.add("A")
    b, pb = await env.add("B")
    pa.push(*[ProviderUnavailable("down")] * 5)
    pb.push("from B")
    ctx = CallContext(
        project_id="proj_f",
        preferred_model=f"{a}:demo:scripted",
        fallback_models=(f"{b}:demo:scripted",),
        max_retries=1,
    )
    result, meta = await env.gateway.generate(ctx, req())
    assert result.text == "from B" and meta.fallback_used and meta.provider_id == b
    assert [x.error_code for x in meta.attempts] == ["unavailable", "unavailable"]
    ev = [e for e in await env.c.bus.query(EventFilter(project_id="proj_f")) if e.type == "RECOVERY_DECISION"]
    assert ev and ev[0].payload["action"] == "change_model" and ev[0].payload["to"].startswith(b)


async def test_auth_failure_skips_retries_and_falls_back(env) -> None:  # type: ignore[no-untyped-def]
    a, pa = await env.add("A")
    b, pb = await env.add("B")
    pa.push(ProviderAuthError("bad key"))
    pb.push("ok")
    result, meta = await env.gateway.generate(
        CallContext(preferred_model=f"{a}:demo:scripted", fallback_models=(f"{b}:demo:scripted",)), req()
    )
    assert result.text == "ok" and env.sleeps == [] and meta.retries == 0


async def test_invalid_structured_output_falls_back_and_failed_attempts_are_still_billed(env) -> None:  # type: ignore[no-untyped-def]
    a, pa = await env.add("A")
    b, pb = await env.add("B")
    pa.push("nope", "nope", "nope")  # 1 try + 2 repairs, all invalid
    pb.push(GOOD)
    ctx = CallContext(
        agent_id="agent_s", preferred_model=f"{a}:demo:scripted", fallback_models=(f"{b}:demo:scripted",)
    )
    result, meta = await env.gateway.generate_structured(ctx, req(), Answer)
    assert result.value == GOOD and meta.fallback_used
    assert len(pa.requests) == 3
    s = await env.c.usage.summary(days=1, group_by="agent")
    assert s.groups[0].calls == 2  # A's failed attempts (recorded once, summed) + B's success
    assert s.groups[0].input_tokens > 0


async def test_refusal_is_terminal_and_never_shopped_around(env) -> None:  # type: ignore[no-untyped-def]
    a, pa = await env.add("A")
    b, pb = await env.add("B")
    pa.push(ProviderRefusal("I can't help with that"))
    pb.push("would have complied")
    with pytest.raises(GatewayError) as info:
        await env.gateway.generate(
            CallContext(preferred_model=f"{a}:demo:scripted", fallback_models=(f"{b}:demo:scripted",)), req()
        )
    assert info.value.code == "refusal" and pb.requests == []


async def test_all_models_failing_raises_a_categorised_error_with_every_attempt(env) -> None:  # type: ignore[no-untyped-def]
    a, pa = await env.add("A")
    b, pb = await env.add("B")
    pa.push(ProviderAuthError("bad key"))
    pb.push(ProviderTimeout("slow"), ProviderTimeout("slow"))
    ctx = CallContext(
        preferred_model=f"{a}:demo:scripted", fallback_models=(f"{b}:demo:scripted",), max_retries=1
    )
    with pytest.raises(GatewayError) as info:
        await env.gateway.generate(ctx, req())
    assert info.value.category is FailureCategory.TIMEOUT  # the last failure decides the category
    assert [x.error_code for x in info.value.attempts] == ["auth_failed", "timeout", "timeout"]


async def test_structured_failure_everywhere_is_invalid_output(env) -> None:  # type: ignore[no-untyped-def]
    _, p = await env.add()
    p.push("x", "y", "z")
    with pytest.raises(GatewayError) as info:
        await env.gateway.generate_structured(CallContext(), req(), Answer)
    assert info.value.category is FailureCategory.INVALID_OUTPUT


async def test_no_provider_configured_is_a_clear_failure(env) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(GatewayError) as info:
        await env.gateway.generate(CallContext(), req())
    assert info.value.code == "no_route" and "Settings" in info.value.message


async def test_budget_stops_the_call_before_it_is_made(env, client: httpx.AsyncClient) -> None:  # type: ignore[no-untyped-def]
    _, p = await env.add()
    p.push("should never be requested")
    body = {**(await client.get("/api/budgets")).json(), "daily_tokens": 5}
    await client.put("/api/budgets", json=body)
    with pytest.raises(GatewayError) as info:
        await env.gateway.generate(CallContext(project_id="proj_b"), req())
    assert info.value.code == "budget_exceeded" and "Budget limit reached" in info.value.message
    assert p.requests == [] and p.remaining == 1
    types = [e.type for e in await env.c.bus.query(EventFilter(project_id="proj_b"))]
    assert "BUDGET_EXCEEDED" in types


async def test_private_calls_never_reach_cloud_providers(
    env, upstream: Upstream, client: httpx.AsyncClient
) -> None:  # type: ignore[no-untyped-def]
    upstream.on("gw.example.com", lambda r: httpx.Response(200, json={"data": [{"id": "cloud-model"}]}))
    await client.post(
        "/api/providers",
        json={
            "kind": "openai_compatible",
            "name": "Cloud",
            "base_url": "https://gw.example.com/v1",
            "default_model": "cloud-model",
        },
    )
    with pytest.raises(GatewayError) as info:
        await env.gateway.generate(CallContext(private=True), req())
    assert info.value.code == "no_route" and "private" in info.value.message
    assert not any(r.url.path.endswith("/chat/completions") for r in upstream.requests)

    _, local = await env.add("Local")
    local.push("local answer")
    result, _ = await env.gateway.generate(CallContext(private=True), req())
    assert result.text == "local answer"
    assert not any(r.url.path.endswith("/chat/completions") for r in upstream.requests)


async def test_streaming_records_usage_and_hides_usage_chunks(env) -> None:  # type: ignore[no-untyped-def]
    _, p = await env.add()
    p.push("streamed reply text here")
    chunks = [c async for c in env.gateway.stream(CallContext(agent_id="agent_st"), req())]
    assert "".join(c.text for c in chunks if c.kind == "text") == "streamed reply text here"
    assert all(c.kind != "usage" for c in chunks) and chunks[-1].kind == "done"
    assert (await env.c.usage.summary(days=1, group_by="agent")).groups[0].calls == 1


async def test_streaming_falls_back_only_before_the_first_chunk(env) -> None:  # type: ignore[no-untyped-def]
    a, _ = await env.add("A")
    b, pb = await env.add("B")

    class FailsBeforeOutput(ScriptedProvider):
        async def stream(self, r):  # type: ignore[no-untyped-def]
            raise ProviderUnavailable("down")
            yield  # pragma: no cover

    env.scripted[a] = FailsBeforeOutput(a)
    env.c.registry.invalidate()
    pb.push("fallback stream")
    ctx = CallContext(preferred_model=f"{a}:demo:scripted", fallback_models=(f"{b}:demo:scripted",))
    chunks = [c async for c in env.gateway.stream(ctx, req())]
    assert "".join(c.text for c in chunks if c.kind == "text") == "fallback stream"

    class FailsMidStream(ScriptedProvider):
        async def stream(self, r):  # type: ignore[no-untyped-def]
            from app.providers.types import StreamChunk

            yield StreamChunk(kind="text", text="partial")
            raise ProviderUnavailable("connection dropped")

    env.scripted[a] = FailsMidStream(a)
    env.c.registry.invalidate()
    pb.push("must not be used")
    got: list[str] = []
    with pytest.raises(GatewayError):
        async for c in env.gateway.stream(ctx, req()):
            got.append(c.text)
    assert got == ["partial"] and pb.remaining == 1

from __future__ import annotations

import httpx
import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadRequest,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderRefusal,
    ProviderUnavailable,
)
from app.providers.types import ChatMessage, GenerateRequest
from tests.providers_helpers import Answer, Recorder, make_client, sse

KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123"


def req(**kw: object) -> GenerateRequest:
    base: dict[str, object] = {
        "model": "claude-sonnet-5-5",
        "system": "You are terse.",
        "messages": [ChatMessage(role="user", content="hi")],
        "max_tokens": 200,
        "temperature": 0.3,
    }
    return GenerateRequest(**{**base, **kw})  # type: ignore[arg-type]


def provider(rec: Recorder) -> AnthropicProvider:
    return AnthropicProvider("prov_a", make_client(rec), api_key=KEY)


def message(content: list[dict[str, object]], **extra: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_1",
            "model": "claude-sonnet-5-5",
            "content": content,
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 11, "output_tokens": 7},
            **extra,
        },
    )


async def test_generate_request_shape_and_parsing() -> None:
    rec = Recorder(message([{"type": "text", "text": "Hello"}, {"type": "text", "text": " there"}]))
    result = await provider(rec).generate(req())
    r = rec.requests[0]
    assert str(r.url) == "https://api.anthropic.com/v1/messages"
    assert r.headers["x-api-key"] == KEY
    assert r.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in r.headers
    body = rec.body()
    assert body == {
        "model": "claude-sonnet-5-5",
        "max_tokens": 200,
        "system": "You are terse.",
        "temperature": 0.3,
        "messages": [{"role": "user", "content": "hi"}],
    }
    assert result.text == "Hello there"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 7)
    assert result.finish_reason == "end_turn"


async def test_thinking_blocks_are_discarded() -> None:
    rec = Recorder(
        message(
            [
                {"type": "thinking", "thinking": "SECRET CHAIN OF THOUGHT", "signature": "x"},
                {"type": "redacted_thinking", "data": "abc"},
                {"type": "text", "text": "answer"},
            ]
        )
    )
    result = await provider(rec).generate(req(reasoning="deep"))
    assert result.text == "answer"
    assert "CHAIN OF THOUGHT" not in result.model_dump_json()
    body = rec.body()
    assert body["thinking"] == {"type": "enabled", "budget_tokens": 8192}
    assert body["max_tokens"] >= 8192 + 1024
    assert "temperature" not in body  # extended thinking requires the default


async def test_light_reasoning_budget() -> None:
    rec = Recorder(message([{"type": "text", "text": "x"}]))
    await provider(rec).generate(req(reasoning="light"))
    assert rec.body()["thinking"]["budget_tokens"] == 2048


async def test_structured_uses_forced_tool_call() -> None:
    rec = Recorder(
        message(
            [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "respond",
                    "input": {"city": "Paris", "population_millions": 2.1},
                }
            ],
            stop_reason="tool_use",
        )
    )
    result = await provider(rec).generate_structured(req(), Answer)
    body = rec.body()
    assert body["tool_choice"] == {"type": "tool", "name": "respond"}
    assert body["tools"][0]["input_schema"]["properties"]["city"]["type"] == "string"
    assert result.value == Answer(city="Paris", population_millions=2.1)
    assert result.attempts == 1


async def test_structured_with_reasoning_uses_schema_in_prompt_not_forced_tool() -> None:
    rec = Recorder(message([{"type": "text", "text": '{"city": "Paris", "population_millions": 2.1}'}]))
    result = await provider(rec).generate_structured(req(reasoning="light"), Answer)
    body = rec.body()
    assert "tool_choice" not in body and "tools" not in body
    assert "JSON Schema" in body["system"]
    assert result.value.city == "Paris"


async def test_structured_repairs_when_tool_input_invalid() -> None:
    rec = Recorder(
        message([{"type": "tool_use", "id": "t1", "name": "respond", "input": {"city": "Paris"}}]),
        message(
            [
                {
                    "type": "tool_use",
                    "id": "t2",
                    "name": "respond",
                    "input": {"city": "Paris", "population_millions": 2.1},
                }
            ]
        ),
    )
    result = await provider(rec).generate_structured(req(), Answer)
    assert result.attempts == 2 and result.repaired
    assert len(rec.requests) == 2
    assert result.usage.input_tokens == 22


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (404, ProviderModelNotFound),
        (400, ProviderBadRequest),
        (429, ProviderRateLimited),
        (500, ProviderUnavailable),
        (529, ProviderUnavailable),
    ],
)
async def test_error_mapping(status: int, exc: type[Exception]) -> None:
    rec = Recorder(httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "nope"}}))
    with pytest.raises(exc):
        await provider(rec).generate(req())


async def test_rate_limit_carries_retry_after_and_is_retryable() -> None:
    rec = Recorder(
        httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "slow down"}})
    )
    with pytest.raises(ProviderRateLimited) as info:
        await provider(rec).generate(req())
    assert info.value.retry_after == 7.0
    assert info.value.retryable


async def test_error_messages_never_contain_the_api_key() -> None:
    rec = Recorder(httpx.Response(401, json={"error": {"message": f"invalid x-api-key: {KEY}"}}))
    with pytest.raises(ProviderAuthError) as info:
        await provider(rec).generate(req())
    assert KEY not in info.value.message
    assert "REDACTED" in info.value.message


async def test_connection_failure_is_unavailable_with_hint() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderUnavailable, match="Could not connect"):
        await AnthropicProvider("p", make_client(boom), api_key=KEY).generate(req())


async def test_refusal_stop_reason() -> None:
    rec = Recorder(message([], stop_reason="refusal"))
    with pytest.raises(ProviderRefusal):
        await provider(rec).generate(req())


async def test_streaming_text_and_usage() -> None:
    rec = Recorder(
        sse(
            (
                "message_start",
                {"type": "message_start", "message": {"usage": {"input_tokens": 9, "output_tokens": 1}}},
            ),
            ("ping", {"type": "ping"}),
            (
                "content_block_delta",
                {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "hmm"}},
            ),
            (
                "content_block_delta",
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
            ),
            (
                "content_block_delta",
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
            ),
            ("message_delta", {"type": "message_delta", "usage": {"output_tokens": 5}}),
            ("message_stop", {"type": "message_stop"}),
        )
    )
    chunks = [c async for c in provider(rec).stream(req())]
    assert rec.body()["stream"] is True
    assert "".join(c.text for c in chunks if c.kind == "text") == "Hello"
    usage = next(c.usage for c in chunks if c.kind == "usage")
    assert usage is not None and (usage.input_tokens, usage.output_tokens) == (9, 5)
    assert chunks[-1].kind == "done"


async def test_streaming_http_error_raises_mapped_error() -> None:
    rec = Recorder(httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(ProviderAuthError):
        [c async for c in provider(rec).stream(req())]


async def test_models_and_token_count() -> None:
    rec = Recorder(
        httpx.Response(
            200,
            json={
                "data": [
                    {"id": "claude-sonnet-5-5", "display_name": "Sonnet"},
                    {"id": "claude-haiku-4-5-20251001"},
                ]
            },
        ),
        httpx.Response(200, json={"input_tokens": 42}),
        httpx.Response(500, json={"error": {"message": "down"}}),
    )
    p = provider(rec)
    models = await p.available_models()
    assert [m.id for m in models] == ["claude-sonnet-5-5", "claude-haiku-4-5-20251001"]
    assert models[0].display_name == "Sonnet"
    assert await p.count_tokens(req()) == 42
    assert await p.count_tokens(req()) > 0  # falls back to the estimate when the endpoint fails


async def test_custom_base_url_and_missing_key() -> None:
    rec = Recorder(message([{"type": "text", "text": "ok"}]))
    p = AnthropicProvider("p", make_client(rec), api_key=None, base_url="http://localhost:9999/")
    await p.generate(req())
    assert str(rec.requests[0].url) == "http://localhost:9999/v1/messages"
    assert "x-api-key" not in rec.requests[0].headers

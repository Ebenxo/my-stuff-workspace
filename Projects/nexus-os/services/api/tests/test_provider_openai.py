from __future__ import annotations

import httpx
import pytest

from app.providers.errors import ProviderAuthError, ProviderBadRequest, ProviderRefusal
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.types import ChatMessage, GenerateRequest
from tests.providers_helpers import Answer, Recorder, make_client, sse

KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"


def req(**kw: object) -> GenerateRequest:
    base: dict[str, object] = {
        "model": "gpt-x",
        "system": "Be brief.",
        "messages": [ChatMessage(role="user", content="hi")],
        "max_tokens": 100,
        "temperature": 0.1,
    }
    return GenerateRequest(**{**base, **kw})  # type: ignore[arg-type]


def completion(content: str | None, **msg: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gpt-x",
            "choices": [{"message": {"content": content, **msg}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )


def openai(rec: Recorder, **kw: object) -> OpenAICompatProvider:
    return OpenAICompatProvider("prov_o", make_client(rec), kind="openai", api_key=KEY, **kw)  # type: ignore[arg-type]


async def test_openai_request_shape() -> None:
    rec = Recorder(completion("Hello"))
    result = await openai(rec).generate(req())
    r = rec.requests[0]
    assert str(r.url) == "https://api.openai.com/v1/chat/completions"
    assert r.headers["authorization"] == f"Bearer {KEY}"
    body = rec.body()
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "hi"},
    ]
    assert body["max_completion_tokens"] == 100 and "max_tokens" not in body
    assert result.text == "Hello"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 4)


async def test_lmstudio_uses_max_tokens_and_needs_no_key() -> None:
    rec = Recorder(completion("ok"))
    p = OpenAICompatProvider(
        "p", make_client(rec), kind="lmstudio", api_key=None, base_url="http://127.0.0.1:1234/v1"
    )
    await p.generate(req())
    assert "authorization" not in rec.requests[0].headers
    assert rec.body()["max_tokens"] == 100 and "max_completion_tokens" not in rec.body()
    assert str(rec.requests[0].url) == "http://127.0.0.1:1234/v1/chat/completions"


async def test_structured_uses_json_schema_response_format() -> None:
    rec = Recorder(completion('{"city": "Paris", "population_millions": 2.1}'))
    result = await openai(rec).generate_structured(req(), Answer)
    rf = rec.body()["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "Answer"
    assert rf["json_schema"]["schema"]["properties"]["city"]["type"] == "string"
    assert result.value.population_millions == 2.1


async def test_structured_downgrades_when_server_rejects_response_format() -> None:
    reject = httpx.Response(
        400, json={"error": {"message": "'response_format' of type 'json_schema' is not supported"}}
    )
    reject2 = httpx.Response(400, json={"error": {"message": "response_format json_object unsupported"}})
    ok = completion('{"city": "Paris", "population_millions": 2.1}')
    rec = Recorder(reject, reject2, ok)
    p = OpenAICompatProvider(
        "p", make_client(rec), kind="openai_compatible", api_key=None, base_url="http://x/v1"
    )
    result = await p.generate_structured(req(), Answer)
    assert result.value.city == "Paris"
    assert [b.get("response_format", {}).get("type") for b in (rec.body(i) for i in range(3))] == [
        "json_schema",
        "json_object",
        None,
    ]
    assert "JSON Schema" in rec.body(2)["messages"][0]["content"]
    # The downgrade is remembered: the next call goes straight to the prompt path.
    rec2 = Recorder(ok)
    p._client = make_client(rec2)
    await p.generate_structured(req(), Answer)
    assert "response_format" not in rec2.body()


async def test_unrelated_bad_request_is_not_swallowed_by_downgrade() -> None:
    rec = Recorder(httpx.Response(400, json={"error": {"message": "context length exceeded"}}))
    with pytest.raises(ProviderBadRequest, match="context length"):
        await openai(rec).generate_structured(req(), Answer)
    assert len(rec.requests) == 1


async def test_refusal_is_reported() -> None:
    rec = Recorder(completion(None, refusal="I can't help with that."))
    with pytest.raises(ProviderRefusal, match="can't help"):
        await openai(rec).generate(req())


async def test_auth_error_redacts_key() -> None:
    rec = Recorder(httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {KEY}"}}))
    with pytest.raises(ProviderAuthError) as info:
        await openai(rec).generate(req())
    assert KEY not in info.value.message


async def test_streaming_deltas_and_usage() -> None:
    rec = Recorder(
        sse(
            ("", {"choices": [{"delta": {"role": "assistant"}}]}),
            ("", {"choices": [{"delta": {"content": "Hel"}}]}),
            ("", {"choices": [{"delta": {"content": "lo"}}]}),
            ("", {"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 2}}),
            ("", "[DONE]"),
        )
    )
    chunks = [c async for c in openai(rec).stream(req())]
    body = rec.body()
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert "".join(c.text for c in chunks if c.kind == "text") == "Hello"
    usage = next(c.usage for c in chunks if c.kind == "usage")
    assert usage is not None and (usage.input_tokens, usage.output_tokens) == (8, 2)


async def test_models_listing_shapes() -> None:
    rec = Recorder(httpx.Response(200, json={"data": [{"id": "gpt-a"}, {"id": "gpt-b"}, {"nope": 1}]}))
    assert [m.id for m in await openai(rec).available_models()] == ["gpt-a", "gpt-b"]
    rec2 = Recorder(httpx.Response(200, json=[{"id": "local-1"}]))
    lm = OpenAICompatProvider("p", make_client(rec2), kind="lmstudio", api_key=None, base_url="http://x/v1")
    models = await lm.available_models()
    assert models[0].id == "local-1" and models[0].local


async def test_html_instead_of_json_is_a_clear_error() -> None:
    rec = Recorder(
        httpx.Response(200, content=b"<html>Please log in</html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(ProviderBadRequest, match="did not return JSON"):
        await openai(rec).generate(req())
    with pytest.raises(ProviderBadRequest, match="did not return JSON"):
        await openai(rec).available_models()


async def test_redirect_responses_are_errors_not_successes() -> None:
    rec = Recorder(httpx.Response(302, headers={"location": "https://elsewhere.example.com/"}))
    with pytest.raises(ProviderBadRequest, match="redirect"):
        await openai(rec).generate(req())


async def test_malformed_stream_frame_is_a_provider_error_not_a_crash() -> None:
    from app.providers.errors import ProviderError

    rec = Recorder(sse(("", {"choices": [{"delta": {"content": "ok"}}]}), ("", "{not json")))
    with pytest.raises(ProviderError, match="malformed streaming data"):
        [c async for c in openai(rec).stream(req())]

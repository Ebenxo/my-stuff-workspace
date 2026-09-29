from __future__ import annotations

import json

import httpx
import pytest

from app.providers.errors import ProviderBadRequest, ProviderRefusal, ProviderUnavailable
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider
from app.providers.types import ChatMessage, GenerateRequest
from tests.providers_helpers import Answer, Recorder, make_client, sse

GKEY = "AIzaSyA1234567890abcdefghijklmnopqrstuvwx"


def req(model: str = "m1", **kw: object) -> GenerateRequest:
    base: dict[str, object] = {
        "model": model,
        "system": "Be brief.",
        "messages": [
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="assistant", content="yo"),
            ChatMessage(role="user", content="again"),
        ],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    return GenerateRequest(**{**base, **kw})  # type: ignore[arg-type]


# ---------------- Ollama ----------------


def ollama_reply(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "llama-x",
            "message": {"role": "assistant", "content": text},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 20,
            "eval_count": 6,
        },
    )


async def test_ollama_generate_shape() -> None:
    rec = Recorder(ollama_reply("hello"))
    p = OllamaProvider("p", make_client(rec))
    result = await p.generate(req("llama-x"))
    assert str(rec.requests[0].url) == "http://127.0.0.1:11434/api/chat"
    body = rec.body()
    assert body["stream"] is False
    assert body["options"] == {"num_predict": 64, "temperature": 0.5}
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert len(body["messages"]) == 4
    assert result.text == "hello"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (20, 6)


async def test_ollama_structured_uses_native_format_schema() -> None:
    rec = Recorder(ollama_reply('{"city": "Paris", "population_millions": 2.1}'))
    result = await OllamaProvider("p", make_client(rec)).generate_structured(req("llama-x"), Answer)
    assert rec.body()["format"]["properties"]["city"]["type"] == "string"
    assert result.value.city == "Paris"


async def test_ollama_streaming_ndjson() -> None:
    lines = [
        {"message": {"content": "Hel"}, "done": False},
        {"message": {"content": "lo"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 2},
    ]
    rec = Recorder(httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode()))
    chunks = [c async for c in OllamaProvider("p", make_client(rec)).stream(req())]
    assert "".join(c.text for c in chunks if c.kind == "text") == "Hello"
    usage = next(c.usage for c in chunks if c.kind == "usage")
    assert usage is not None and (usage.input_tokens, usage.output_tokens) == (5, 2)


async def test_ollama_models_are_local_and_down_server_gives_hint() -> None:
    rec = Recorder(httpx.Response(200, json={"models": [{"name": "llama3:8b"}, {"name": "qwen:7b"}]}))
    models = await OllamaProvider("p", make_client(rec)).available_models()
    assert [m.id for m in models] == ["llama3:8b", "qwen:7b"] and all(m.local for m in models)

    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderUnavailable, match="Is it running"):
        await OllamaProvider("p", make_client(refuse)).available_models()


# ---------------- Gemini ----------------


def gem_reply(text: str, **extra: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 14, "candidatesTokenCount": 3},
            **extra,
        },
    )


def gemini(rec: Recorder) -> GeminiProvider:
    return GeminiProvider("prov_g", make_client(rec), api_key=GKEY)


async def test_gemini_request_shape_and_key_stays_out_of_the_url() -> None:
    rec = Recorder(gem_reply("hello"))
    result = await gemini(rec).generate(req("gemini-x"))
    r = rec.requests[0]
    assert str(r.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent"
    assert r.headers["x-goog-api-key"] == GKEY
    assert GKEY not in str(r.url) and not r.url.query
    body = rec.body()
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["systemInstruction"] == {"parts": [{"text": "Be brief."}]}
    assert body["generationConfig"] == {"maxOutputTokens": 64, "temperature": 0.5}
    assert result.text == "hello"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (14, 3)


async def test_gemini_structured_native_schema_then_fallback() -> None:
    ok = gem_reply('{"city": "Paris", "population_millions": 2.1}')
    rec = Recorder(ok)
    result = await gemini(rec).generate_structured(req("gemini-x"), Answer)
    cfg = rec.body()["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseJsonSchema"]["properties"]["population_millions"]["type"] == "number"
    assert result.value.city == "Paris"

    reject = httpx.Response(
        400, json={"error": {"message": "Unknown field responseJsonSchema in generation_config schema"}}
    )
    rec2 = Recorder(reject, ok)
    p = gemini(rec2)
    result2 = await p.generate_structured(req("gemini-x"), Answer)
    assert result2.value.city == "Paris"
    assert "responseJsonSchema" not in rec2.body()["generationConfig"]
    assert "JSON Schema" in rec2.body()["systemInstruction"]["parts"][0]["text"]


async def test_gemini_unrelated_400_propagates() -> None:
    rec = Recorder(httpx.Response(400, json={"error": {"message": "API key expired"}}))
    with pytest.raises(ProviderBadRequest, match="expired"):
        await gemini(rec).generate_structured(req("gemini-x"), Answer)


async def test_gemini_thoughts_dropped_and_blocked_prompts_reported() -> None:
    rec = Recorder(
        httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "PRIVATE THOUGHT", "thought": True}, {"text": "answer"}]}}
                ]
            },
        )
    )
    assert (await gemini(rec).generate(req("g"))).text == "answer"
    blocked = Recorder(httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ProviderRefusal, match="SAFETY"):
        await gemini(blocked).generate(req("g"))


async def test_gemini_streaming_uses_sse_alt() -> None:
    rec = Recorder(
        sse(
            ("", {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]}),
            (
                "",
                {
                    "candidates": [{"content": {"parts": [{"text": "lo"}]}}],
                    "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
                },
            ),
        )
    )
    chunks = [c async for c in gemini(rec).stream(req("g"))]
    assert rec.requests[0].url.params["alt"] == "sse"
    assert rec.requests[0].url.path.endswith(":streamGenerateContent")
    assert "".join(c.text for c in chunks if c.kind == "text") == "Hello"


async def test_gemini_models_filter_and_count_tokens() -> None:
    rec = Recorder(
        httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-a",
                        "displayName": "A",
                        "inputTokenLimit": 1000,
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {"name": "models/embed-b", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
        ),
        httpx.Response(200, json={"totalTokens": 33}),
    )
    p = gemini(rec)
    models = await p.available_models()
    assert [m.id for m in models] == ["gemini-a"] and models[0].context_length == 1000
    assert await p.count_tokens(req("gemini-a")) == 33

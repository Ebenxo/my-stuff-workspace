from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.providers.errors import InvalidStructuredOutput, ProviderError
from app.providers.jsonutil import describe_validation_error, extract_json
from app.providers.scripted import ScriptedProvider
from app.providers.types import ChatMessage, GenerateRequest, estimate_request_tokens, estimate_tokens
from tests.providers_helpers import Answer


def request() -> GenerateRequest:
    return GenerateRequest(
        model="demo:scripted", messages=[ChatMessage(role="user", content="capital of France?")]
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": [1, 2]}\n```', {"a": [1, 2]}),
        ('Sure! Here you go:\n{"a": {"b": 2}} hope that helps', {"a": {"b": 2}}),
        ("[1, 2, 3]", [1, 2, 3]),
        ('{"text": "has } brace"}', {"text": "has } brace"}),
    ],
)
def test_extract_json(text: str, expected: object) -> None:
    assert extract_json(text) == expected


@pytest.mark.parametrize("text", ["", "no json here", "{broken", '{"a": '])
def test_extract_json_rejects_garbage(text: str) -> None:
    with pytest.raises(ValueError):
        extract_json(text)


def test_validation_description_never_echoes_input() -> None:
    secret = "sk-ant-api03-supersecretsupersecretsupersecret"
    try:
        Answer.model_validate({"city": 5, "population_millions": secret})
    except Exception as exc:
        text = describe_validation_error(exc)
    assert secret not in text
    assert "population_millions" in text


async def test_structured_success_first_try() -> None:
    p = ScriptedProvider().push(Answer(city="Paris", population_millions=2.1))
    result = await p.generate_structured(request(), Answer)
    assert result.value == Answer(city="Paris", population_millions=2.1)
    assert result.attempts == 1
    assert not result.repaired
    assert result.usage.total > 0


async def test_structured_repairs_invalid_output_then_succeeds() -> None:
    p = ScriptedProvider().push(
        "not json at all", '{"city": "Paris"}', Answer(city="Paris", population_millions=2.1)
    )
    result = await p.generate_structured(request(), Answer)
    assert result.attempts == 3
    assert result.repaired
    # Each repair turn carries the model's previous reply and a description of what was wrong.
    last = p.requests[-1].messages
    assert last[-1].role == "user" and "could not be used" in last[-1].content
    assert last[-2].role == "assistant" and last[-2].content == '{"city": "Paris"}'
    assert "population_millions" in last[-1].content
    # Usage is the sum over every attempt, not just the last one.
    assert result.usage.input_tokens == sum(estimate_request_tokens(r) for r in p.requests)


async def test_structured_gives_up_after_bounded_attempts() -> None:
    p = ScriptedProvider().push("nope", "still nope", "never")
    with pytest.raises(InvalidStructuredOutput) as info:
        await p.generate_structured(request(), Answer, max_repairs=2)
    assert len(p.requests) == 3
    assert "Answer" in info.value.message


async def test_structured_provider_errors_propagate_unchanged() -> None:
    p = ScriptedProvider().push(ProviderError("boom"))
    with pytest.raises(ProviderError, match="boom"):
        await p.generate_structured(request(), Answer)


async def test_scripted_provider_streams_and_exhausts() -> None:
    p = ScriptedProvider().push("hello streaming world, in chunks")
    chunks = [c async for c in p.stream(request())]
    assert "".join(c.text for c in chunks if c.kind == "text") == "hello streaming world, in chunks"
    assert chunks[-1].kind == "done"
    with pytest.raises(ProviderError, match="exhausted"):
        await p.generate(request())


async def test_scripted_handlers_and_callables() -> None:
    class Plan(BaseModel):
        steps: int

    p = ScriptedProvider()
    p.on(Plan, lambda req: Plan(steps=len(req.messages)))
    assert (await p.generate_structured(request(), Plan)).value.steps == 1
    p.push(lambda req: f"echo:{req.messages[-1].content}")
    assert (await p.generate(request())).text == "echo:capital of France?"


async def test_test_connection_reports_failure_and_success() -> None:
    ok = await ScriptedProvider().test_connection()
    assert ok.ok and ok.models_found == 1

    class Down(ScriptedProvider):
        async def available_models(self):  # type: ignore[no-untyped-def]
            raise ProviderError("refused")

    bad = await Down().test_connection()
    assert not bad.ok and bad.error_code == "provider_error" and "refused" in bad.detail


def test_estimate_tokens_is_conservative() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 35) == 10
    assert estimate_tokens("a") == 1

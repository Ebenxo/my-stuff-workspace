from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.providers.catalog import cost_usd, enrich, infer_tier, is_local_provider
from app.providers.errors import NoRouteError
from app.providers.router import ModelRef, ModelRouter, RouteRequest, TaskClass
from app.providers.types import ModelInfo
from app.schemas.providers import (
    ModelOverride,
    ModelPrice,
    ProviderOptions,
    RoutingPrefer,
    RoutingRule,
    RoutingRules,
    RoutingWhen,
)

# ---------------- catalog ----------------


@pytest.mark.parametrize(
    ("model", "tier"),
    [
        ("claude-haiku-4-5-20251001", "fast"),
        ("gpt-mini", "fast"),
        ("gemini-flash", "fast"),
        ("llama3:8b", "fast"),
        ("claude-opus-5-5", "strong"),
        ("claude-fable-5-1", "strong"),
        ("o3-thing", "strong"),
        ("qwen:72b", "strong"),
        ("claude-sonnet-5-5", "balanced"),
        ("mystery-model", "balanced"),
    ],
)
def test_tier_inference(model: str, tier: str) -> None:
    assert infer_tier(model) == tier


def test_local_detection() -> None:
    assert is_local_provider("ollama", None)
    assert is_local_provider("lmstudio", None)
    assert is_local_provider("openai_compatible", "http://localhost:8000/v1")
    assert is_local_provider("openai_compatible", "http://127.0.0.1:8000")
    assert not is_local_provider("openai_compatible", "https://api.example.com/v1")
    assert not is_local_provider(
        "openai_compatible", "http://192.168.1.20:1234/v1"
    )  # LAN is not "this machine"
    assert not is_local_provider("anthropic", None)


def test_enrich_local_is_free_and_overrides_win() -> None:
    base = ModelInfo(id="llama3:8b", provider_id="p")
    local = enrich(base, kind="ollama", base_url=None, options=None)
    assert local.local and local.input_cost_per_mtok == 0.0 and local.tier == "fast"

    opts = ProviderOptions(
        models={"m": ModelOverride(tier="strong", context_length=1000, price=ModelPrice(input=3, output=15))}
    )
    cloud = enrich(ModelInfo(id="m", provider_id="p"), kind="anthropic", base_url=None, options=opts)
    assert not cloud.local and cloud.tier == "strong" and cloud.context_length == 1000
    assert (cloud.input_cost_per_mtok, cloud.output_cost_per_mtok) == (3, 15)


def test_cost_is_unknown_not_zero_without_a_price() -> None:
    assert cost_usd(1000, 1000, ModelInfo(id="m", provider_id="p")) is None
    assert cost_usd(1000, 1000, None) is None
    priced = ModelInfo(id="m", provider_id="p", input_cost_per_mtok=2.0, output_cost_per_mtok=10.0)
    assert cost_usd(1_000_000, 500_000, priced) == pytest.approx(7.0)
    free = ModelInfo(id="m", provider_id="p", input_cost_per_mtok=0.0, output_cost_per_mtok=0.0)
    assert cost_usd(5000, 5000, free) == 0.0


# ---------------- router ----------------


class FakeRegistry:
    def __init__(self, providers: list[tuple[Any, ...]]) -> None:
        # (provider_id, default_model, models[, kind])
        self._data = [
            (SimpleNamespace(id=p[0], default_model=p[1], kind=p[3] if len(p) > 3 else "openai"), p[2])
            for p in providers
        ]

    async def all_models(self, *, enabled_only: bool = True):  # type: ignore[no-untyped-def]
        return self._data


def m(
    pid: str,
    mid: str,
    *,
    tier: str | None = None,
    local: bool = False,
    ctx: int | None = None,
    vision: bool | None = None,
) -> ModelInfo:
    return ModelInfo(
        id=mid,
        provider_id=pid,
        tier=tier or infer_tier(mid),
        local=local,
        context_length=ctx,
        supports_vision=vision,
    )  # type: ignore[arg-type]


def router(providers, rules: list[RoutingRule] | None = None) -> ModelRouter:  # type: ignore[no-untyped-def]
    async def get_rules() -> RoutingRules:
        return RoutingRules(rules=rules or [])

    return ModelRouter(FakeRegistry(providers), get_rules)  # type: ignore[arg-type]


CLOUD = ("cloud", "big-sonnet", [m("cloud", "small-haiku"), m("cloud", "big-sonnet"), m("cloud", "top-opus")])
LOCAL = ("local", "llama3:8b", [m("local", "llama3:8b", local=True), m("local", "qwen:72b", local=True)])


def test_model_ref_parsing() -> None:
    ref = ModelRef.parse("prov_1:llama3:8b")
    assert (ref.provider_id, ref.model) == ("prov_1", "llama3:8b")
    assert str(ref) == "prov_1:llama3:8b"
    for bad in ("", "nocolon", ":x", "x:"):
        with pytest.raises(ValueError):
            ModelRef.parse(bad)


async def test_no_providers_gives_actionable_error() -> None:
    with pytest.raises(NoRouteError, match="Settings"):
        await router([]).route(RouteRequest())


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (TaskClass.FORMATTING, "small-haiku"),
        (TaskClass.GENERAL, "big-sonnet"),
        (TaskClass.CODING, "top-opus"),
        (TaskClass.PLANNING, "top-opus"),
    ],
)
async def test_default_policy_by_task_class(task: TaskClass, expected: str) -> None:
    route = await router([CLOUD]).route(RouteRequest(task_class=task))
    assert route.primary.model == expected
    assert "default policy" in route.reason


async def test_nearest_tier_when_exact_is_missing() -> None:
    only_balanced_and_strong = ("p", None, [m("p", "mid-sonnet"), m("p", "top-opus")])
    route = await router([only_balanced_and_strong]).route(RouteRequest(task_class=TaskClass.FORMATTING))
    assert route.primary.model == "mid-sonnet"  # nearest to "fast"


async def test_agent_preference_beats_rules_and_falls_through_when_unavailable() -> None:
    rule = RoutingRule(
        name="coding", when=RoutingWhen(task_class="coding"), prefer=RoutingPrefer(model="cloud:top-opus")
    )
    r = router([CLOUD], [rule])
    route = await r.route(RouteRequest(task_class=TaskClass.CODING, preferred="cloud:small-haiku"))
    assert (route.primary.model, route.reason) == ("small-haiku", "agent preference")
    route = await r.route(RouteRequest(task_class=TaskClass.CODING, preferred="cloud:gone"))
    assert route.primary.model == "top-opus" and "routing rule" in route.reason


async def test_manual_override_wins_and_unknown_override_is_an_error() -> None:
    r = router([CLOUD])
    route = await r.route(
        RouteRequest(
            task_class=TaskClass.CODING, preferred="cloud:big-sonnet", manual_override="cloud:small-haiku"
        )
    )
    assert route.primary.model == "small-haiku" and route.reason == "manual override"
    with pytest.raises(NoRouteError, match="not available"):
        await r.route(RouteRequest(manual_override="cloud:nope"))


async def test_private_tasks_only_ever_use_local_models() -> None:
    r = router([CLOUD, LOCAL])
    route = await r.route(RouteRequest(task_class=TaskClass.CODING, private=True))
    assert route.primary.provider_id == "local" and route.primary.model == "qwen:72b"
    assert all(f.provider_id == "local" for f in route.fallbacks)
    assert "private" in route.reason


async def test_private_with_no_local_model_refuses_instead_of_leaking() -> None:
    with pytest.raises(NoRouteError, match="private"):
        await router([CLOUD]).route(RouteRequest(private=True))


async def test_private_task_cannot_be_forced_onto_a_cloud_model_by_override_or_preference() -> None:
    r = router([CLOUD, LOCAL])
    with pytest.raises(NoRouteError, match="not local"):
        await r.route(RouteRequest(private=True, manual_override="cloud:top-opus"))
    route = await r.route(RouteRequest(private=True, preferred="cloud:top-opus"))
    assert route.primary.provider_id == "local"  # the cloud preference is ignored, not honoured


async def test_user_rules_first_match_wins_and_unresolvable_rules_are_skipped() -> None:
    rules = [
        RoutingRule(
            name="ghost",
            when=RoutingWhen(task_class="formatting"),
            prefer=RoutingPrefer(model="cloud:does-not-exist"),
        ),
        RoutingRule(
            name="format-local",
            when=RoutingWhen(task_class="formatting"),
            prefer=RoutingPrefer(local=True, tier="fast"),
        ),
        RoutingRule(
            name="never-reached",
            when=RoutingWhen(task_class="formatting"),
            prefer=RoutingPrefer(model="cloud:top-opus"),
        ),
    ]
    route = await router([CLOUD, LOCAL], rules).route(RouteRequest(task_class=TaskClass.FORMATTING))
    assert route.primary == ModelRef("local", "llama3:8b")
    assert "format-local" in route.reason


async def test_rule_conditions() -> None:
    rules = [
        RoutingRule(
            name="private", when=RoutingWhen(private=True), prefer=RoutingPrefer(provider_id="local")
        ),
        RoutingRule(
            name="big-input",
            when=RoutingWhen(min_input_tokens=50_000),
            prefer=RoutingPrefer(model="cloud:top-opus"),
        ),
    ]
    r = router([CLOUD, LOCAL], rules)
    assert "big-input" in (await r.route(RouteRequest(input_tokens=60_000))).reason
    assert "routing rule" not in (await r.route(RouteRequest(input_tokens=10))).reason
    assert (await r.route(RouteRequest(private=True))).primary.provider_id == "local"


async def test_context_window_filters_models_known_to_be_too_small() -> None:
    providers = [
        ("p", None, [m("p", "tiny-mini", ctx=4_000), m("p", "big-opus", ctx=200_000), m("p", "mystery-x")])
    ]
    r = router(providers)
    route = await r.route(RouteRequest(task_class=TaskClass.FORMATTING, input_tokens=50_000))
    assert route.primary.model != "tiny-mini"
    # If nothing is known to fit, keep everything and let the provider report the overflow.
    only_small = [("p", None, [m("p", "tiny-mini", ctx=4_000)])]
    assert (await router(only_small).route(RouteRequest(input_tokens=50_000))).primary.model == "tiny-mini"


async def test_long_document_prefers_largest_known_context() -> None:
    providers = [
        ("p", None, [m("p", "a-opus", ctx=200_000), m("p", "b-gemini", ctx=1_000_000), m("p", "c-unknown")])
    ]
    route = await router(providers).route(RouteRequest(task_class=TaskClass.LONG_DOCUMENT))
    assert route.primary.model == "b-gemini"
    assert "context" in route.reason


async def test_fallbacks_agent_first_then_other_provider_defaults_deduped_and_capped() -> None:
    many = [(f"p{i}", f"m{i}", [m(f"p{i}", f"m{i}")]) for i in range(8)]
    route = await router(many).route(
        RouteRequest(preferred="p0:m0", fallbacks=["p5:m5", "p5:m5", "p0:m0", "nonsense"])
    )
    assert route.primary == ModelRef("p0", "m0")
    assert route.fallbacks[0] == ModelRef("p5", "m5")
    assert len(route.fallbacks) == 4 and len(set(route.fallbacks)) == 4
    assert ModelRef("p0", "m0") not in route.fallbacks


async def test_vision_requirement_prefers_capable_models() -> None:
    providers = [
        ("p", None, [m("p", "text-only-sonnet", vision=False), m("p", "seeing-sonnet", vision=True)])
    ]
    route = await router(providers).route(RouteRequest(needs_vision=True))
    assert route.primary.model == "seeing-sonnet"


DEMO = ("demo", "demo:scripted", [m("demo", "demo:scripted", tier="balanced", local=True)], "demo")


async def test_the_demo_provider_never_answers_real_work_automatically() -> None:
    r = router([DEMO, CLOUD])
    route = await r.route(RouteRequest(task_class=TaskClass.GENERAL))
    assert route.primary.provider_id == "cloud"
    assert all(f.provider_id != "demo" for f in route.fallbacks)  # not even as a fallback
    private = router([DEMO, LOCAL])
    assert (await private.route(RouteRequest(private=True))).primary.provider_id == "local"


async def test_with_only_the_demo_provider_real_work_has_no_route() -> None:
    with pytest.raises(NoRouteError, match="demo provider only runs the demo project"):
        await router([DEMO]).route(RouteRequest())


async def test_the_demo_is_used_when_chosen_and_never_falls_back_to_a_real_model() -> None:
    route = await router([DEMO, CLOUD]).route(RouteRequest(manual_override="demo:demo:scripted"))
    assert (
        str(route.primary) == "demo:demo:scripted"
        and route.fallbacks == []
        and route.reason == "manual override"
    )


async def test_tests_can_opt_in_to_routing_to_scripted_models() -> None:
    r = router([DEMO])
    r.auto_route_demo = True
    assert (await r.route(RouteRequest())).primary.provider_id == "demo"

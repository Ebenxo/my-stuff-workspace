from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.providers.types import ModelInfo, TokenUsage
from app.providers.usage import UsageService
from app.repositories.events import EventFilter

PRICED = ModelInfo(id="m", provider_id="p", input_cost_per_mtok=10.0, output_cost_per_mtok=30.0)
UNPRICED = ModelInfo(id="u", provider_id="p")
LOCAL = ModelInfo(id="l", provider_id="p", input_cost_per_mtok=0.0, output_cost_per_mtok=0.0, local=True)


def usage_svc(app: FastAPI) -> UsageService:
    return app.state.container.usage  # type: ignore[no-any-return]


async def set_budgets(client: httpx.AsyncClient, **kw: object) -> None:
    body = {**(await client.get("/api/budgets")).json(), **kw}
    assert (await client.put("/api/budgets", json=body)).status_code == 200


async def rec(svc: UsageService, info: ModelInfo, i: int, o: int, **kw: object) -> None:
    await svc.record(
        provider_id="p",
        model=info.id,
        usage=TokenUsage(input_tokens=i, output_tokens=o),
        latency_ms=5,
        info=info,
        **kw,
    )  # type: ignore[arg-type]


async def test_cost_known_unknown_and_free(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    await rec(svc, PRICED, 1_000_000, 100_000)  # 10 + 3 = 13 USD
    await rec(svc, UNPRICED, 5000, 500)
    await rec(svc, LOCAL, 9000, 900)
    s = (await client.get("/api/usage/summary", params={"group_by": "model"})).json()
    by = {g["key"]: g for g in s["groups"]}
    assert by["m"]["cost_usd"] == pytest.approx(13.0) and by["m"]["unknown_cost_calls"] == 0
    assert (
        by["u"]["cost_usd"] == 0.0 and by["u"]["unknown_cost_calls"] == 1
    )  # unknown is flagged, never counted as free
    assert by["l"]["cost_usd"] == 0.0 and by["l"]["unknown_cost_calls"] == 0  # local is known-free
    assert s["total_cost_usd"] == pytest.approx(13.0) and s["unknown_cost_calls"] == 1
    assert s["total_calls"] == 3 and s["total_tokens"] == 1_100_000 + 5500 + 9900


async def test_summary_groupings_and_validation(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    await rec(svc, PRICED, 100, 10, agent_id="agent_a", project_id="proj_1", purpose="agent")
    await rec(svc, PRICED, 200, 20, agent_id="agent_b", project_id="proj_1", purpose="planning")
    await rec(svc, PRICED, 300, 30, agent_id="agent_a", project_id="proj_2", purpose="agent")
    for group, expected in (
        ("agent", {"agent_a": 2, "agent_b": 1}),
        ("project", {"proj_1": 2, "proj_2": 1}),
        ("purpose", {"agent": 2, "planning": 1}),
    ):
        keys = {
            g["key"]: g["calls"]
            for g in (await client.get("/api/usage/summary", params={"group_by": group})).json()["groups"]
        }
        assert keys == expected
    days = (await client.get("/api/usage/summary", params={"group_by": "day"})).json()["groups"]
    assert len(days) == 1 and days[0]["calls"] == 3
    assert (await client.get("/api/usage/summary", params={"group_by": "nonsense"})).status_code == 422


async def test_usd_budget_blocks_and_warns_once(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    await set_budgets(client, daily_usd=10.0, warn_at_fraction=0.8)
    await rec(svc, PRICED, 700_000, 0)  # $7 spent
    ok = await svc.check_budget(est_input_tokens=100_000, est_output_tokens=0, info=PRICED)  # +$1 -> 8 = 80%
    assert ok.allowed and len(ok.warnings) == 1 and "daily USD" in ok.warnings[0]
    again = await svc.check_budget(est_input_tokens=100_000, est_output_tokens=0, info=PRICED)
    assert again.allowed and again.warnings == []  # warned once per period, not on every call
    over = await svc.check_budget(est_input_tokens=400_000, est_output_tokens=0, info=PRICED)  # +$4 -> 11
    assert not over.allowed and "would be exceeded" in over.exceeded[0]
    types = [
        e.type
        for e in await app.state.container.bus.query(
            EventFilter(types=frozenset({"BUDGET_WARNING", "BUDGET_EXCEEDED"}))
        )
    ]
    assert types == ["BUDGET_WARNING", "BUDGET_EXCEEDED"]


async def test_hard_stop_off_reports_but_allows(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    await set_budgets(client, daily_usd=1.0, hard_stop=False)
    verdict = await svc.check_budget(est_input_tokens=1_000_000, est_output_tokens=0, info=PRICED)
    assert verdict.allowed and verdict.exceeded


async def test_token_budget_counts_unknown_price_calls_but_usd_budget_cannot(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    svc = usage_svc(app)
    await set_budgets(client, daily_tokens=10_000, daily_usd=0.01)
    await rec(svc, UNPRICED, 9_000, 500)
    # USD limit cannot see an unpriced call, but the token limit still does.
    v = await svc.check_budget(est_input_tokens=1000, est_output_tokens=0, info=UNPRICED)
    assert (
        not v.allowed and any("tokens" in e for e in v.exceeded) and not any("USD" in e for e in v.exceeded)
    )


async def test_per_project_and_per_agent_scopes(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    await set_budgets(client, per_project_monthly_usd={"proj_1": 5.0}, per_agent_monthly_usd={"agent_x": 2.0})
    await rec(svc, PRICED, 400_000, 0, project_id="proj_1", agent_id="agent_x")  # $4 in proj_1 by agent_x
    await rec(
        svc, PRICED, 900_000, 0, project_id="proj_2", agent_id="agent_y"
    )  # $9 elsewhere: must not count
    p1 = await svc.check_budget(
        est_input_tokens=200_000, est_output_tokens=0, info=PRICED, project_id="proj_1"
    )  # 4+2 > 5
    assert not p1.allowed and "project proj_1" in p1.exceeded[0]
    p2 = await svc.check_budget(
        est_input_tokens=200_000, est_output_tokens=0, info=PRICED, project_id="proj_2"
    )
    assert p2.allowed  # proj_2 has no cap of its own
    ax = await svc.check_budget(
        est_input_tokens=100_000, est_output_tokens=0, info=PRICED, agent_id="agent_x"
    )  # 4+1 > 2
    assert not ax.allowed and "agent agent_x" in ax.exceeded[0]
    ay = await svc.check_budget(
        est_input_tokens=100_000, est_output_tokens=0, info=PRICED, agent_id="agent_y"
    )
    assert ay.allowed


async def test_expensive_call_flag(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    await set_budgets(client, expensive_call_usd=0.5)
    assert (
        await svc.check_budget(est_input_tokens=100_000, est_output_tokens=0, info=PRICED)
    ).expensive  # $1
    assert not (await svc.check_budget(est_input_tokens=1000, est_output_tokens=0, info=PRICED)).expensive
    assert not (
        await svc.check_budget(est_input_tokens=10_000_000, est_output_tokens=0, info=UNPRICED)
    ).expensive


async def test_usage_events_are_emitted_without_content(app: FastAPI) -> None:
    svc = usage_svc(app)
    await rec(svc, PRICED, 10, 5, agent_id="agent_a", project_id="proj_9")
    events = await app.state.container.bus.query(EventFilter(project_id="proj_9"))
    assert events[0].type == "USAGE_RECORDED"
    assert set(events[0].payload) == {
        "model",
        "provider_id",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "estimated_tokens",
    }


async def test_a_projects_own_monthly_budget_is_enforced(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = usage_svc(app)
    p = (
        await client.post("/api/projects", json={"name": "Capped", "settings": {"monthly_budget_usd": 3.0}})
    ).json()
    other = (await client.post("/api/projects", json={"name": "Uncapped"})).json()
    await rec(svc, PRICED, 200_000, 0, project_id=p["id"])  # $2 of $3
    over = await svc.check_budget(
        est_input_tokens=200_000, est_output_tokens=0, info=PRICED, project_id=p["id"]
    )
    assert not over.allowed and f"project {p['id']}" in over.exceeded[0]
    assert (
        await svc.check_budget(
            est_input_tokens=200_000, est_output_tokens=0, info=PRICED, project_id=other["id"]
        )
    ).allowed

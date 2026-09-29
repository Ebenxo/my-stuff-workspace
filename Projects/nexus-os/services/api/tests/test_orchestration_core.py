from __future__ import annotations

from typing import Any

import pytest

from app.agents.builtin import BUILTIN_AGENTS
from app.core.failures import FailureCategory
from app.orchestration.graph import CycleError, TaskGraph
from app.orchestration.recovery import Failure, decide
from app.orchestration.strategy import estimate
from app.orchestration.validator import MAX_TASKS, PlanInvalid, validate_plan
from app.schemas.orchestration import PlanResult, ReviewResult, TaskStatus, VerificationResult
from app.tools.builtin import builtin_tools
from app.tools.registry import ToolRegistry

S = TaskStatus


def registry() -> ToolRegistry:
    r = ToolRegistry()
    for t in builtin_tools():
        r.register(t)
    return r


def plan(*tasks: dict[str, Any], complexity: str = "medium", **kw: Any) -> PlanResult:
    return PlanResult.model_validate(
        {
            "objective": "Do it",
            "tasks": [{"description": "", **t} for t in tasks],
            "completion_criteria": ["It is done"],
            "complexity": complexity,
            **kw,
        }
    )


def check(p: PlanResult, **kw: Any) -> Any:
    return validate_plan(p, BUILTIN_AGENTS, registry(), **kw)


# ------------------------------------------------------------------ graph


def test_topological_order_and_ready_set() -> None:
    g = TaskGraph.build({"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]})
    assert g.topo_order() == ["a", "b", "c", "d"]
    assert g.ready() == ["a"]
    g.status["a"] = S.COMPLETED
    assert g.ready() == ["b", "c"]
    g.status["b"] = S.COMPLETED
    g.status["c"] = S.SKIPPED  # a skipped optional dependency still lets dependents start
    assert g.ready() == ["d"]
    assert g.depth() == 3 and g.width() == 2 and g.sinks() == ["d"]
    assert g.descendants("a") == {"b", "c", "d"}


def test_failed_dependencies_doom_their_dependents() -> None:
    g = TaskGraph.build({"a": [], "b": ["a"], "c": []}, {"a": S.FAILED})
    assert g.doomed() == ["b"] and g.ready() == ["c"]


def test_cycles_are_reported_with_the_path() -> None:
    with pytest.raises(CycleError) as err:
        TaskGraph.build({"a": ["c"], "b": ["a"], "c": ["b"]}).topo_order()
    assert set(err.value.cycle) == {"a", "b", "c"} and err.value.cycle[0] == err.value.cycle[-1]


def test_unknown_dependencies_are_refused() -> None:
    with pytest.raises(ValueError, match="unknown"):
        TaskGraph.build({"a": ["ghost"]})


def test_settled_only_when_every_task_is_final() -> None:
    g = TaskGraph.build({"a": [], "b": []}, {"a": S.COMPLETED, "b": S.BLOCKED})
    assert not g.settled()
    g.status["b"] = S.SKIPPED
    assert g.settled()


# ------------------------------------------------------------------ validator


def test_a_good_plan_is_accepted_and_normalised() -> None:
    v = check(
        plan(
            {
                "key": "t1",
                "title": " Research ",
                "agent": "researcher",
                "tools": ["web_search", "run_command"],
            },
            {"key": "t2", "title": "Write", "agent": "writer", "depends_on": ["t1", "t1"], "review": True},
            {
                "key": "t3",
                "title": "Tidy",
                "agent": "file_manager",
                "tools": ["delete_file"],
                "depends_on": ["t2"],
            },
        )
    )
    t1, t2, t3 = v.plan.tasks
    assert v.order == ["t1", "t2", "t3"]
    assert t1.title == "Research" and t1.tools == ["web_search"]  # the researcher cannot run commands
    assert any("run_command" in w for w in v.warnings)
    assert t2.depends_on == ["t1"] and t2.review
    assert t3.approval_required  # delete_file always asks, so the plan says so up front


@pytest.mark.parametrize(
    ("tasks", "fragment"),
    [
        ([{"key": "t1", "title": "x", "agent": "wizard"}], "unknown agent 'wizard'"),
        ([{"key": "t1", "title": "x", "agent": "verifier"}], "fixed role"),
        ([{"key": "t1", "title": "x", "agent": "orchestrator"}], "fixed role"),
        ([{"key": "t1", "title": "x", "agent": "writer", "depends_on": ["t1"]}], "depends on itself"),
        ([{"key": "t1", "title": "x", "agent": "writer", "depends_on": ["t9"]}], "unknown task 't9'"),
        (
            [{"key": "t1", "title": "x", "agent": "writer"}, {"key": "t1", "title": "y", "agent": "coder"}],
            "unique",
        ),
        (
            [
                {"key": "a", "title": "x", "agent": "writer", "depends_on": ["b"]},
                {"key": "b", "title": "y", "agent": "coder", "depends_on": ["a"]},
            ],
            "cycle",
        ),
    ],
)
def test_bad_plans_are_rejected_with_a_reason(tasks: list[dict[str, Any]], fragment: str) -> None:
    with pytest.raises(PlanInvalid) as err:
        check(plan(*tasks))
    assert any(fragment in i for i in err.value.issues), err.value.issues


def test_a_small_objective_may_not_fan_out() -> None:
    many = [{"key": f"t{i}", "title": "x", "agent": "writer"} for i in range(5)]
    with pytest.raises(PlanInvalid, match="at most 4"):
        check(plan(*many, complexity="small"))
    check(plan(*many[:4], complexity="small"))
    check(plan(*many, complexity="medium"))
    too_many = [{"key": f"t{i}", "title": "x", "agent": "writer"} for i in range(MAX_TASKS + 1)]
    with pytest.raises(PlanInvalid):
        check(plan(*too_many, complexity="large"))


def test_follow_up_plans_build_on_existing_tasks() -> None:
    p = plan({"key": "f1", "title": "Fix", "agent": "writer", "depends_on": ["t2"]})
    assert check(p, existing_keys={"t1", "t2"}, follow_up=True).order == ["f1"]
    with pytest.raises(PlanInvalid, match="already used"):
        check(plan({"key": "t1", "title": "x", "agent": "writer"}), existing_keys={"t1"})


def test_disabled_agents_and_tools_are_respected() -> None:
    writer = next(a for a in BUILTIN_AGENTS if a.slug == "writer")
    agents = [
        a if a.slug != "writer" else writer.model_copy(update={"status": "disabled"}) for a in BUILTIN_AGENTS
    ]
    with pytest.raises(PlanInvalid, match="disabled"):
        validate_plan(plan({"key": "t1", "title": "x", "agent": "writer"}), agents, registry())
    v = check(
        plan({"key": "t1", "title": "x", "agent": "researcher", "tools": ["web_search"]}),
        disabled_tools={"web_search"},
    )
    assert v.plan.tasks[0].tools == []


def test_the_critic_is_never_asked_to_review_itself() -> None:
    v = check(plan({"key": "t1", "title": "Audit", "agent": "critic", "review": True}))
    assert v.plan.tasks[0].review is False


# ------------------------------------------------------------------ strategy


def test_strategy_names_the_shape_and_estimates_cost() -> None:
    one = estimate(plan({"key": "t1", "title": "x", "agent": "writer"}))
    assert one.name == "single_agent" and one.task_count == 1
    reviewed = estimate(plan({"key": "t1", "title": "x", "agent": "writer", "review": True}))
    assert reviewed.name == "reviewer" and reviewed.estimated_tokens > one.estimated_tokens
    chain = estimate(
        plan(
            {"key": "t1", "title": "x", "agent": "researcher"},
            {"key": "t2", "title": "y", "agent": "writer", "depends_on": ["t1"]},
        )
    )
    assert chain.name == "pipeline" and chain.depth == 2 and "2 specialists" in chain.rationale
    fan = estimate(
        plan(
            {"key": "a", "title": "x", "agent": "researcher"},
            {"key": "b", "title": "y", "agent": "data_analyst"},
            {"key": "c", "title": "z", "agent": "writer", "depends_on": ["a", "b"]},
        )
    )
    assert fan.name == "parallel" and fan.width == 2


# ------------------------------------------------------------------ recovery


def fail(category: FailureCategory, code: str = "x", attempts: int = 1, optional: bool = False) -> Failure:
    return Failure(category, code, "msg", attempts, 2, optional)


@pytest.mark.parametrize(
    ("failure", "action"),
    [
        (fail(FailureCategory.PERMISSION_DENIED), "block"),
        (fail(FailureCategory.PERMISSION_DENIED, optional=True), "skip"),
        (fail(FailureCategory.UNKNOWN, "agent_reported_failure"), "block"),
        (fail(FailureCategory.TIMEOUT, "step_limit"), "resume"),
        (fail(FailureCategory.TIMEOUT, "runtime_limit"), "resume"),
        (fail(FailureCategory.TIMEOUT, "token_budget", attempts=2), "block"),
        (fail(FailureCategory.MODEL_FAILURE, "loop_detected"), "retry"),
        (fail(FailureCategory.MODEL_FAILURE, "unavailable"), "retry"),
        (fail(FailureCategory.MODEL_FAILURE, "unavailable", attempts=2), "block"),
        (fail(FailureCategory.MODEL_FAILURE, "budget_exceeded"), "block"),
        (fail(FailureCategory.MODEL_FAILURE, "auth_failed"), "block"),
        (fail(FailureCategory.MODEL_FAILURE, "refusal", optional=True), "skip"),
        (fail(FailureCategory.INVALID_OUTPUT, "invalid_output"), "retry"),
        (fail(FailureCategory.TOOL_FAILURE), "retry"),
        (fail(FailureCategory.TOOL_FAILURE, attempts=2, optional=True), "skip"),
        (fail(FailureCategory.UNKNOWN, "internal_error"), "retry"),
        (fail(FailureCategory.UNKNOWN, "internal_error", attempts=2), "block"),
    ],
)
def test_recovery_table(failure: Failure, action: str) -> None:
    d = decide(failure)
    assert d.action == action and d.reason


# ------------------------------------------------------------------ result contracts


def test_a_revise_verdict_must_say_what_to_fix() -> None:
    with pytest.raises(ValueError, match="list the issues"):
        ReviewResult(verdict="revise", summary="no")
    ok = ReviewResult.model_validate(
        {
            "verdict": "revise",
            "summary": "s",
            "issues": [{"severity": "major", "description": "Missing sources"}],
        }
    )
    assert ok.issues[0].blocking


def test_pass_requires_every_criterion_met() -> None:
    with pytest.raises(ValueError, match="every criterion"):
        VerificationResult.model_validate(
            {"verdict": "PASS", "summary": "s", "criteria": [{"criterion": "c", "met": False}]}
        )

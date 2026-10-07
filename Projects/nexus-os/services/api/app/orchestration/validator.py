"""PlanValidator: a plan from a model is a *proposal*. This decides whether it can run, as written.

Hard problems (cycles, unknown agents, too many tasks for the objective's size) make the plan invalid;
the Planner gets the list and one chance to fix it. Soft problems (a tool the agent cannot use) are
corrected and reported as warnings.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.core.risk import RiskLevel
from app.orchestration.graph import CycleError, TaskGraph
from app.schemas.agents import AgentDefinition
from app.schemas.orchestration import PlanResult, PlanTask
from app.tools.registry import ToolRegistry, matches

MAX_TASKS = 12
MAX_FOLLOW_UP_TASKS = 4
# Cheapest effective plan: an objective the planner itself calls small may not fan out widely.
MAX_TASKS_BY_COMPLEXITY = {"trivial": 2, "small": 4, "medium": 8, "large": MAX_TASKS}
# These agents have fixed roles in the lifecycle and are never assigned plan tasks.
RESERVED_AGENTS = frozenset({"orchestrator", "planner", "verifier"})


class PlanInvalid(ValueError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass
class ValidatedPlan:
    plan: PlanResult
    order: list[str]  # task keys, dependencies first
    warnings: list[str] = field(default_factory=list)


def _agent_tools(agent: AgentDefinition, registry: ToolRegistry, disabled: set[str]) -> dict[str, RiskLevel]:
    return {
        t.name: t.risk_level
        for t in registry.all()
        if t.name not in disabled and any(matches(p, t.name) for p in agent.tools)
    }


def validate_plan(
    plan: PlanResult,
    agents: Iterable[AgentDefinition],
    registry: ToolRegistry,
    *,
    disabled_tools: set[str] | None = None,
    existing_keys: Iterable[str] = (),
    follow_up: bool = False,
) -> ValidatedPlan:
    disabled = disabled_tools or set()
    by_slug = {a.slug: a for a in agents}
    existing = set(existing_keys)
    issues: list[str] = []
    warnings: list[str] = []

    limit = MAX_FOLLOW_UP_TASKS if follow_up else min(MAX_TASKS, MAX_TASKS_BY_COMPLEXITY[plan.complexity])
    if len(plan.tasks) > limit:
        what = "a follow-up plan" if follow_up else f"a {plan.complexity} objective"
        issues.append(
            f"The plan has {len(plan.tasks)} tasks; {what} may have at most {limit}. "
            "Merge steps one specialist can do together."
        )

    keys = [t.key for t in plan.tasks]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        issues.append(f"Task keys must be unique; repeated: {', '.join(dupes)}.")
    clash = sorted(set(keys) & existing)
    if clash:
        issues.append(f"Task keys already used in this objective: {', '.join(clash)}.")

    known = set(keys) | existing
    fixed: list[PlanTask] = []
    for t in plan.tasks:
        agent = by_slug.get(t.agent)
        if agent is None:
            issues.append(f"{t.key}: unknown agent '{t.agent}'. Use one of: {', '.join(sorted(by_slug))}.")
        elif t.agent in RESERVED_AGENTS:
            issues.append(f"{t.key}: '{t.agent}' has a fixed role and cannot be given plan tasks.")
        elif agent.status == "disabled":
            issues.append(f"{t.key}: {agent.name} is disabled.")
        for d in t.depends_on:
            if d == t.key:
                issues.append(f"{t.key} depends on itself.")
            elif d not in known:
                issues.append(f"{t.key} depends on unknown task '{d}'.")

        tools = list(dict.fromkeys(x.strip() for x in t.tools if x.strip()))
        approval = t.approval_required
        review = t.review
        if agent is not None:
            usable = _agent_tools(agent, registry, disabled)
            dropped = [x for x in tools if x not in usable]
            if dropped:
                warnings.append(
                    f"{t.key}: {agent.name} cannot use {', '.join(dropped)}; removed from the plan."
                )
            tools = [x for x in tools if x in usable]
            for name in tools:
                tool = registry.get(name)
                if tool is not None and (tool.requires_approval or usable[name] >= RiskLevel.HIGH):
                    approval = True
            if t.agent == "critic" and review:
                review = False  # the Critic does not review itself
        fixed.append(
            t.model_copy(
                update={
                    "title": t.title.strip(),
                    "description": t.description.strip(),
                    "tools": tools,
                    "depends_on": list(dict.fromkeys(t.depends_on)),
                    "approval_required": approval,
                    "review": review,
                }
            )
        )

    order: list[str] = []
    if not dupes:
        # Existing tasks are fixed points: they have no dependencies inside this plan.
        deps = {t.key: [d for d in t.depends_on if d in set(keys)] for t in plan.tasks}
        try:
            order = TaskGraph.build(deps).topo_order()
        except CycleError as exc:
            issues.append(
                f"The tasks form a cycle ({' -> '.join(exc.cycle)}); dependencies must flow one way."
            )
        except ValueError:
            pass  # unknown dependencies are already reported above

    if issues:
        raise PlanInvalid(issues)
    return ValidatedPlan(plan.model_copy(update={"tasks": fixed}), order, warnings)

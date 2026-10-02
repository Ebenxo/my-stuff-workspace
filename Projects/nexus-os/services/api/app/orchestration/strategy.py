"""StrategyEstimator: name the execution shape of a validated plan and estimate what it costs.

The shape follows the plan: the estimator never adds agents. Its job is to make the cost of a plan
visible before it runs and to explain in one sentence why this many agents are involved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.orchestration.graph import TaskGraph
from app.schemas.orchestration import PlanResult

# Rough tokens per task by complexity (a model turn per step, a few steps per task).
TOKENS_BY_COMPLEXITY = {"trivial": 6_000, "small": 15_000, "medium": 40_000, "large": 90_000}
REVIEW_TOKENS = 12_000
VERIFY_TOKENS = 15_000


@dataclass(frozen=True)
class Strategy:
    name: str  # single_agent | pipeline | parallel | reviewer
    rationale: str
    task_count: int
    agents: list[str]
    depth: int
    width: int
    reviews: int
    estimated_tokens: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def estimate(plan: PlanResult) -> Strategy:
    graph = TaskGraph.build(
        {t.key: [d for d in t.depends_on if d in {x.key for x in plan.tasks}] for t in plan.tasks}
    )
    agents = list(dict.fromkeys(t.agent for t in plan.tasks))
    reviews = sum(1 for t in plan.tasks if t.review)
    depth, width, n = graph.depth(), graph.width(), len(plan.tasks)
    tokens = (
        sum(TOKENS_BY_COMPLEXITY[t.complexity] for t in plan.tasks) + reviews * REVIEW_TOKENS + VERIFY_TOKENS
    )

    if n == 1:
        name = "reviewer" if reviews else "single_agent"
        why = "One specialist can do this in a single task" + (
            ", with a review of its work." if reviews else "."
        )
    elif width > 1:
        name = "parallel"
        why = f"{width} tasks are independent and can run at the same time"
    elif reviews:
        name = "reviewer"
        why = "The work is sequential and parts of it get a quality review"
    else:
        name = "pipeline"
        why = "Each step needs the previous one's result"
    if n > 1:
        why += f"; {len(agents)} specialist{'s' if len(agents) != 1 else ''} across {n} tasks"
        why += f", {reviews} reviewed." if reviews and name != "reviewer" else "."
    return Strategy(name, why, n, agents, depth, width, reviews, tokens)

"""Pure workflow pieces: expressions and templates, graph validation, cron, input coercion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import InvalidRequestError
from app.scheduler import cron
from app.schemas.workflows import WorkflowDefinition
from app.workflows.expr import ExpressionError, evaluate, render, render_prompt, render_value, root_names
from app.workflows.service import coerce_inputs
from app.workflows.validate import starter_definition, validate_definition

V: dict[str, Any] = {
    "inputs": {"topic": "tea", "n": 3, "urgent": True},
    "nodes": {
        "fetch": {
            "output": {"items": ["a", "b", "c"], "meta": {"count": 3}, "summary": "Found 3"},
            "status": "COMPLETED",
        }
    },
}


# ---------------------------------------------------------------- expressions


@pytest.mark.parametrize(
    ("expr", "want"),
    [
        ("inputs.topic", "tea"),
        ("inputs.n * 2 + 1", 7),
        ("len(nodes.fetch.output.items) > 2 and inputs.urgent", True),
        ("nodes.fetch.output.items[1]", "b"),
        ("nodes.fetch.output['meta']['count']", 3),
        ("nodes.fetch.output.missing", None),
        ("default(nodes.fetch.output.missing, 'none')", "none"),
        ("upper(inputs.topic) if inputs.urgent else inputs.topic", "TEA"),
        ("'b' in nodes.fetch.output.items", True),
        ("join(nodes.fetch.output.items, ' / ')", "a / b / c"),
        ("{'topic': inputs.topic, 'k': [1, 2]}", {"topic": "tea", "k": [1, 2]}),
        ("not inputs.urgent or null", None),
        ("contains(lower('Hello World'), 'world')", True),
    ],
)
def test_expressions_read_plain_data(expr: str, want: Any) -> None:
    assert evaluate(expr, V) == want


@pytest.mark.parametrize(
    ("expr", "why"),
    [
        ("inputs.__class__", "'_'"),
        ("inputs.topic.__len__()", "'_'"),
        ("open('x')", "Only these functions"),
        ("inputs.topic.upper()", "Only these functions"),
        ("[x for x in nodes.fetch.output.items]", "not allowed"),
        ("lambda: 1", "not allowed"),
        ("secret", "Unknown name 'secret'"),
        ("'a' * 1000000", "too long"),
        ("2 ** 64", "not allowed"),
        ("nodes.fetch.output.items[0:2]", "Slices"),
        ("1 / 0", "Division by zero"),
        ("inputs.topic.x.y", "Cannot read"),
        ("", "empty"),
        ("(" * 300, "Not a valid"),
    ],
)
def test_expressions_refuse_anything_beyond_data(expr: str, why: str) -> None:
    with pytest.raises(ExpressionError, match=why):
        evaluate(expr, V)


def test_templates_render_text_and_keep_types_for_whole_holes() -> None:
    assert render("About {{ inputs.topic }} ({{ inputs.n }} items, urgent: {{ inputs.urgent }})", V) == (
        "About tea (3 items, urgent: true)"
    )
    assert render("{{ nodes.fetch.output.meta }}", V) == '{"count": 3}'
    args = render_value(
        {"path": "files/{{ inputs.topic }}.md", "count": "{{ inputs.n }}", "tags": ["{{ inputs.topic }}"]}, V
    )
    assert args == {"path": "files/tea.md", "count": 3, "tags": ["tea"]}
    assert render_value({"plain": "no holes", "n": 5}, V) == {"plain": "no holes", "n": 5}


def test_agent_prompts_get_other_steps_values_as_data_not_instructions() -> None:
    p = render_prompt("Write about {{ inputs.topic }} using {{ nodes.fetch.output.summary }}.", V)
    assert (
        p.text == "Write about tea using [the value of nodes.fetch.output.summary, provided below as data]."
    )
    assert p.data == [("nodes.fetch.output.summary", "Found 3")]
    assert root_names("len(nodes.a.output) > inputs.n and true") == {"nodes", "inputs"}


# ---------------------------------------------------------------- validation


def graph(
    nodes: list[dict[str, Any]],
    edges: list[tuple[str, str] | tuple[str, str, str]],
    inputs: list[dict[str, Any]] | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "inputs": inputs or [],
            "nodes": nodes,
            "edges": [
                {"id": f"e{i}", "source": e[0], "target": e[1], **({"branch": e[2]} if len(e) == 3 else {})}
                for i, e in enumerate(edges)
            ],
        }
    )


START = {"id": "start", "type": "trigger"}


def messages(d: WorkflowDefinition, **kw: Any) -> list[str]:
    return [i.message for i in validate_definition(d, **kw).issues]


def test_the_starter_workflow_is_valid() -> None:
    assert validate_definition(starter_definition(), agents={"writer"}, tools=set(), workflows=set()).ok


def test_structure_problems_are_explained() -> None:
    assert "exactly one start" in messages(graph([{"id": "a", "type": "transform"}], []))[0]
    two = messages(graph([START, {"id": "s2", "type": "trigger"}], []))
    assert any("Only one start" in m for m in two)
    loop = graph(
        [START, {"id": "a", "type": "transform"}, {"id": "b", "type": "transform"}],
        [("start", "a"), ("a", "b"), ("b", "a")],
    )
    assert any("form a loop" in m for m in messages(loop))
    orphan = graph([START, {"id": "lonely", "type": "output"}], [])
    assert any("lonely is not connected" in m for m in messages(orphan))
    bad_edges = graph(
        [
            START,
            {"id": "a", "type": "transform"},
            {"id": "c", "type": "condition", "config": {"expression": "true"}},
        ],
        [("start", "a", "true"), ("a", "c"), ("c", "ghost"), ("start", "start"), ("a", "start")],
    )
    got = messages(bad_edges)
    assert any("Only conditions and approvals" in m for m in got)
    assert any("does not exist" in m for m in got)
    assert any("cannot connect to itself" in m for m in got)
    assert any("Nothing can lead into the start" in m for m in got)
    unlabelled = graph(
        [
            START,
            {"id": "c", "type": "condition", "config": {"expression": "true"}},
            {"id": "x", "type": "output"},
        ],
        [("start", "c"), ("c", "x")],
    )
    assert any("'true' or the 'false' outcome" in m for m in messages(unlabelled))


def test_configuration_expressions_and_references_are_checked() -> None:
    d = graph(
        [
            START,
            {"id": "a", "type": "agent", "config": {"agent": "ghostwriter", "prompt": "Hi {{ inputs.( }}"}},
            {"id": "t", "type": "tool", "config": {"tool": "launch_rocket", "arguments": {}}},
            {"id": "c", "type": "condition", "config": {"expression": "import os"}},
            {
                "id": "l",
                "type": "loop",
                "config": {"items": "inputs.list", "body": {"type": "agent", "config": {"agent": "writer"}}},
            },
            {"id": "w", "type": "subworkflow", "config": {"workflow_id": "wf_self"}},
            {"id": "d", "type": "delay", "config": {"seconds": 0}},
        ],
        [("start", "a"), ("start", "t"), ("start", "c"), ("start", "l"), ("start", "w"), ("start", "d")],
    )
    got = messages(d, agents={"writer"}, tools={"read_file"}, workflows={"wf_self"}, self_id="wf_self")
    assert any("no available agent called 'ghostwriter'" in m for m in got)
    assert any("{{ inputs.( }}" in m for m in got)
    assert any("no enabled tool called 'launch_rocket'" in m for m in got)
    assert any(m.startswith("import os:") for m in got)
    assert any(m.startswith("body.prompt") for m in got)
    assert any("cannot run itself" in m for m in got)
    assert any(m.startswith("seconds") for m in got)


# ---------------------------------------------------------------- cron


NOON = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)  # a Tuesday


@pytest.mark.parametrize(
    ("expr", "after", "want"),
    [
        ("0 9 * * *", NOON, datetime(2026, 9, 30, 9, 0, tzinfo=UTC)),
        ("*/15 * * * *", NOON, datetime(2026, 9, 29, 12, 15, tzinfo=UTC)),
        (
            "0 9 * * 1-5",
            datetime(2026, 10, 2, 12, tzinfo=UTC),
            datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
        ),  # Fri → Mon
        ("30 8 1 * *", NOON, datetime(2026, 10, 1, 8, 30, tzinfo=UTC)),
        ("0 0 29 2 *", NOON, datetime(2028, 2, 29, 0, 0, tzinfo=UTC)),
        ("@hourly", NOON, datetime(2026, 9, 29, 13, 0, tzinfo=UTC)),
        ("0 12 * jan,oct sun", NOON, datetime(2026, 10, 4, 12, 0, tzinfo=UTC)),  # October Sundays only
        (
            "0 9 13 * fri",
            NOON,
            datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        ),  # day 13 OR Friday: the Friday comes first
    ],
)
def test_next_run_times(expr: str, after: datetime, want: datetime) -> None:
    assert cron.next_after(cron.parse(expr), after) == want


def test_time_zones_and_daylight_saving() -> None:
    spec = cron.parse("0 9 * * *")
    # 09:00 in London is 08:00 UTC in summer and 09:00 UTC in winter
    assert cron.next_after(spec, datetime(2026, 10, 20, 12, tzinfo=UTC), "Europe/London") == datetime(
        2026, 10, 21, 8, tzinfo=UTC
    )
    assert cron.next_after(spec, datetime(2026, 10, 26, 12, tzinfo=UTC), "Europe/London") == datetime(
        2026, 10, 27, 9, tzinfo=UTC
    )
    # 01:30 does not exist on the spring-forward day in London: that day is skipped
    gap = cron.parse("30 1 * * *")
    assert cron.next_after(gap, datetime(2026, 3, 28, 12, tzinfo=UTC), "Europe/London") == datetime(
        2026, 3, 30, 0, 30, tzinfo=UTC
    )
    # 01:30 happens twice on the fall-back day (25 Oct 2026): it fires once, at the first one
    daily = cron.upcoming(gap, datetime(2026, 10, 24, 12, tzinfo=UTC), "Europe/London", count=2)
    assert daily == [datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 26, 1, 30, tzinfo=UTC)]
    hourly = cron.upcoming(
        cron.parse("30 * * * *"), datetime(2026, 10, 24, 23, 0, tzinfo=UTC), "Europe/London", count=3
    )
    assert hourly == [
        datetime(2026, 10, 24, 23, 30, tzinfo=UTC),
        datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
        datetime(2026, 10, 25, 2, 30, tzinfo=UTC),
    ]
    runs = cron.upcoming(cron.parse("0 */6 * * *"), NOON, count=3)
    assert [r.hour for r in runs] == [18, 0, 6]


@pytest.mark.parametrize(
    ("expr", "why"),
    [
        ("0 9 * *", "five fields"),
        ("61 * * * *", "between 0 and 59"),
        ("0 25 * * *", "between 0 and 23"),
        ("0 9 * * funday", "not a valid weekday"),
        ("*/0 * * * *", "not a valid step"),
        ("5-2 * * * *", "goes backwards"),
        ("0 0 31 2 *", "never runs"),
    ],
)
def test_bad_expressions_are_explained(expr: str, why: str) -> None:
    with pytest.raises(cron.CronError, match=why):
        cron.next_after(cron.parse(expr), NOON)


def test_descriptions() -> None:
    d = lambda e: cron.describe(cron.parse(e))  # noqa: E731
    assert d("0 9 * * *") == "Every day at 09:00"
    assert d("0 9 * * 1-5") == "Weekdays at 09:00"
    assert d("30 18 * * sat,sun") == "Weekends at 18:30"
    assert d("0 9 * * mon") == "Every Monday at 09:00"
    assert d("0 7 1 * *") == "Monthly on day 1 at 07:00"
    assert d("@hourly") == "Every hour"
    assert d("15 * * * *") == "Every hour at 15 minutes past"
    assert d("0 */6 * * *") == "Every 6 hours at :00"
    assert d("* * * * *") == "Every minute"
    assert d("5 4 3 2 *") == "On the schedule '5 4 3 2 *'"
    with pytest.raises(cron.CronError, match="Unknown time zone"):
        cron.zone("Mars/Olympus")


# ---------------------------------------------------------------- inputs


def test_inputs_are_checked_filled_and_converted() -> None:
    d = WorkflowDefinition.model_validate(
        {
            "inputs": [
                {"name": "topic", "type": "text"},
                {"name": "count", "type": "number", "required": False, "default": 3},
                {"name": "urgent", "type": "boolean", "required": False},
            ]
        }
    )
    assert coerce_inputs(d, {"topic": "tea", "count": "5", "urgent": "yes"}) == {
        "topic": "tea",
        "count": 5,
        "urgent": True,
    }
    assert coerce_inputs(d, {"topic": "tea"}) == {"topic": "tea", "count": 3, "urgent": None}
    with pytest.raises(InvalidRequestError, match="'topic' is required"):
        coerce_inputs(d, {})
    with pytest.raises(InvalidRequestError, match="no input called extra"):
        coerce_inputs(d, {"topic": "x", "extra": 1})
    with pytest.raises(InvalidRequestError, match="must be a number"):
        coerce_inputs(d, {"topic": "x", "count": "lots"})

"""The built-in demo: "Research three AI coding assistants and create a comparison report."

Everything here is explicitly demo material. The three products are fictional and every file says so.
The model is the scripted demo provider, chosen by a manual override so it can never answer anything
else, and it never falls back to a real model. Everything else is real: the planner, validator,
orchestrator, agents, tools, permissions, artifacts, events and verifier all run their normal code.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ConflictError
from app.files.fs import WorkspaceFS
from app.providers.registry import ProviderRegistry
from app.providers.scripted import DEMO_MODEL, ScriptBook, ScriptedProvider
from app.schemas.orchestration import ObjectiveCreate, ObjectiveOut
from app.schemas.projects import ProjectCreate
from app.schemas.providers import ProviderCreate
from app.services.objectives import ObjectiveService
from app.services.projects import ProjectService
from app.services.providers import ProviderService

DEMO_OBJECTIVE = "Research three AI coding assistants and create a comparison report."
DEMO_PROJECT = "Demo: AI coding assistants"
DEMO_PROVIDER = "Demo (scripted)"
REPORT = "ai-coding-assistants-comparison.md"
LABEL = (
    "> DEMO DATA: a fictional product invented for the NEXUS demo. Not a real company, product or price.\n\n"
)

NOTES = {
    "files/notes/alpha-code.md": LABEL
    + "# Alpha Code\n\n- Pricing: $10 per user per month; free for open-source maintainers\n"
    "- Features: inline completions, chat in the editor, repository-wide search\n- Limits: cloud only, no self-hosting\n",
    "files/notes/beta-pair.md": LABEL
    + "# Beta Pair\n\n- Pricing: $19 per user per month; enterprise plan on request\n"
    "- Features: pair-programming agent, runs tests, reviews pull requests\n- Limits: self-hosting only on the enterprise plan\n",
    "files/notes/gamma-dev.md": LABEL + "# Gamma Dev\n\n- Pricing: $15 per user per month\n"
    "- Features: local model support, offline mode, terminal assistant\n- Limits: smaller context window than the others\n",
}


def _report(gamma_price: str) -> str:
    return (
        "# AI coding assistants: comparison (demo)\n\n"
        "_Demo report about fictional products, written by the NEXUS demo._\n\n"
        "## Pricing\n\n| Assistant | Price | Source |\n|---|---|---|\n"
        "| Alpha Code | $10 per user per month (free for open-source maintainers) | files/notes/alpha-code.md |\n"
        "| Beta Pair | $19 per user per month | files/notes/beta-pair.md |\n"
        f"| Gamma Dev | {gamma_price} | files/notes/gamma-dev.md |\n\n"
        "## Features\n\n| Assistant | Strengths | Limits |\n|---|---|---|\n"
        "| Alpha Code | Inline completions, editor chat, repository search | Cloud only |\n"
        "| Beta Pair | Pair-programming agent, runs tests, reviews pull requests | Self-hosting only on enterprise |\n"
        "| Gamma Dev | Local models, offline mode, terminal assistant | Smaller context window |\n\n"
        "## Recommendation\n\nChoose Gamma Dev for offline or private work, Beta Pair for review-heavy teams, "
        "and Alpha Code for the lowest price.\n"
    )


def _call(tool: str, args: dict[str, Any], summary: str) -> dict[str, Any]:
    return {"summary": summary, "action": {"type": "tool_call", "tool": tool, "arguments": args}}


def _finish(result: dict[str, Any], summary: str = "Finishing") -> dict[str, Any]:
    return {"summary": summary, "action": {"type": "finish", "result": result}}


CRITERIA = [
    "A comparison report is saved as an artifact",
    "It covers all three assistants",
    "It compares pricing and features",
    "Every fact names its source note",
]


def build_demo_book() -> ScriptBook:
    book = ScriptBook()
    book.add(
        "Planner",
        _call("list_directory", {"path": "files/notes"}, "Looking at the research notes in the project"),
        _finish(
            {
                "objective": "Compare three AI coding assistants on pricing and features and save a sourced report.",
                "assumptions": ["The three notes in files/notes/ are the sources to use (demo data)."],
                "constraints": ["Use only facts from the notes; mark anything missing instead of guessing."],
                "complexity": "small",
                "tasks": [
                    {
                        "key": "t1",
                        "title": "Extract pricing and features from the notes",
                        "description": "Read the three notes and list each assistant's price, features and limits, citing the note.",
                        "agent": "researcher",
                        "tools": ["list_directory", "read_file"],
                        "expected_outputs": ["Facts per assistant, each with its source note"],
                        "complexity": "small",
                    },
                    {
                        "key": "t2",
                        "title": "Write the comparison report",
                        "description": "Write a Markdown report with a pricing table, a features table and a short recommendation. Cite sources.",
                        "agent": "writer",
                        "depends_on": ["t1"],
                        "tools": ["create_markdown"],
                        "expected_outputs": [f"artifacts/{REPORT}"],
                        "review": True,
                        "complexity": "small",
                    },
                ],
                "risks": ["The notes may be incomplete; gaps must be marked, not filled in."],
                "required_approvals": [],
                "completion_criteria": CRITERIA,
            },
            "Plan: research, then a reviewed report",
        ),
    )
    book.add(
        "Researcher",
        _call("read_file", {"path": "files/notes/alpha-code.md"}, "Reading the Alpha Code note"),
        _call("read_file", {"path": "files/notes/beta-pair.md"}, "Reading the Beta Pair note"),
        _call("read_file", {"path": "files/notes/gamma-dev.md"}, "Reading the Gamma Dev note"),
        _finish(
            {
                "status": "completed",
                "summary": "Extracted pricing, features and limits for all three assistants from the notes.",
                "outputs": [
                    {
                        "kind": "data",
                        "name": "facts",
                        "value": "Alpha Code: $10/user/month; completions, chat, repo search; cloud only (alpha-code.md). "
                        "Beta Pair: $19/user/month; agent, runs tests, reviews PRs; self-hosting on enterprise (beta-pair.md). "
                        "Gamma Dev: $15/user/month; local models, offline, terminal; smaller context (gamma-dev.md).",
                    }
                ],
            },
            "Facts extracted",
        ),
    )
    book.add(
        "Writer",
        _call(
            "create_markdown",
            {"name": REPORT, "content": _report("—"), "note": "First draft"},
            "Saving the first draft",
        ),
        _finish(
            {"status": "completed", "summary": "Wrote the comparison report (first draft)."}, "Draft saved"
        ),
    )
    book.add(
        "Critic",
        _call("read_file", {"path": f"artifacts/{REPORT}"}, "Reading the report itself"),
        _finish(
            {
                "verdict": "revise",
                "summary": "Good structure and sourcing, but one price is missing.",
                "issues": [
                    {
                        "severity": "major",
                        "category": "completeness",
                        "location": "Pricing table, Gamma Dev row",
                        "description": "Gamma Dev's price is missing although its note gives it ($15 per user per month).",
                        "suggestion": "Add the price and keep the source column.",
                    }
                ],
                "checks": {"correctness": True, "completeness": False, "formatting": True},
            },
            "Found a missing price",
        ),
    )
    book.add(
        "Writer",
        _call(
            "create_markdown",
            {"name": REPORT, "content": _report("$15 per user per month"), "note": "Added Gamma Dev's price"},
            "Saving the corrected report",
        ),
        _finish(
            {"status": "completed", "summary": "Added Gamma Dev's price with its source (second version)."},
            "Fixed",
        ),
    )
    book.add(
        "Critic",
        _call("read_file", {"path": f"artifacts/{REPORT}"}, "Checking the revision"),
        _finish(
            {
                "verdict": "approve",
                "summary": "All three assistants are covered with sourced pricing and features.",
                "issues": [],
            },
            "Approved",
        ),
    )
    book.add(
        "Verifier",
        _call("list_directory", {"path": "artifacts"}, "Looking for the deliverable"),
        _call("read_file", {"path": f"artifacts/{REPORT}"}, "Reading the report to check each criterion"),
        _finish(
            {
                "verdict": "PASS",
                "summary": "The report exists, covers all three assistants, compares pricing and features, and cites a note for every row.",
                "criteria": [
                    {"criterion": CRITERIA[0], "met": True, "evidence": f"artifacts/{REPORT} (version 2)"},
                    {
                        "criterion": CRITERIA[1],
                        "met": True,
                        "evidence": "Alpha Code, Beta Pair and Gamma Dev rows in both tables",
                    },
                    {"criterion": CRITERIA[2], "met": True, "evidence": "Pricing table and Features table"},
                    {
                        "criterion": CRITERIA[3],
                        "met": True,
                        "evidence": "Source column cites files/notes/*.md",
                    },
                ],
                "missing_requirements": [],
            },
            "Verified",
        ),
    )
    return book


class DemoService:
    def __init__(
        self,
        *,
        projects: ProjectService,
        providers: ProviderService,
        registry: ProviderRegistry,
        objectives: ObjectiveService,
    ) -> None:
        self._projects = projects
        self._providers = providers
        self._registry = registry
        self._objectives = objectives

    async def start(self) -> ObjectiveOut:
        """Create (or reuse) the demo project and start the demo objective with a fresh script."""
        project = next((p for p in await self._projects.list_all(status="active") if p.is_demo), None)
        if project is None:
            project = await self._projects.create(
                ProjectCreate(
                    name=DEMO_PROJECT,
                    description="Built-in demo with fictional products. Everything here is demo data.",
                    icon="sparkles",
                ),
                is_demo=True,
            )
        running = [
            o
            for o in await self._objectives.list_objectives(project_id=project.id, limit=20)
            if not o.status.terminal
        ]
        if running:
            raise ConflictError("The demo is already running. Open it from the demo project.")
        fs = WorkspaceFS(await self._projects.project_dir(project.id))
        for rel, text in NOTES.items():
            fs.write_text(rel, text)

        provider = next((p for p in await self._providers.list_all() if p.kind == "demo"), None)
        if provider is None:
            provider = await self._providers.create(
                ProviderCreate(kind="demo", name=DEMO_PROVIDER, default_model=DEMO_MODEL)
            )
        adapter = await self._registry.get_provider(provider.id)
        if isinstance(adapter, ScriptedProvider):
            adapter.fallback = build_demo_book()
        return await self._objectives.create(
            ObjectiveCreate(
                project_id=project.id,
                text=DEMO_OBJECTIVE,
                run_mode="review_plan",
                model=f"{provider.id}:{DEMO_MODEL}",
            )
        )

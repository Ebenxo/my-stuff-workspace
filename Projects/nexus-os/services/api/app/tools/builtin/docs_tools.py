"""Artifact tools: finished deliverables, stored with version history."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import InvalidRequestError
from app.core.risk import RiskLevel
from app.schemas.runtime import ArtifactType
from app.tools.base import Capability, ToolContext, ToolDefinition, ToolError


class CreateDocumentArgs(BaseModel):
    name: str = Field(
        description="File name for the deliverable, e.g. 'competitor-report.md'.",
        min_length=1,
        max_length=120,
    )
    content: str = Field(description="The full content.", max_length=5_000_000)
    type: ArtifactType = Field(
        default="document",
        description="document, report, code, json, dataset, spreadsheet, website (a single self-contained HTML file), chart (SVG), presentation.",
    )
    note: str = Field(default="", max_length=300, description="What changed in this version.")


class CreateMarkdownArgs(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(max_length=5_000_000)
    note: str = Field(default="", max_length=300)


async def _save(ctx: ToolContext, name: str, content: str, type_: ArtifactType, note: str) -> dict[str, Any]:
    if not ctx.project_id:
        raise ToolError("Artifacts need a project.", code="no_project")
    try:
        w = await ctx.artifacts.save(
            project_id=ctx.project_id,
            name=name,
            type_=type_,
            content=content,
            agent_id=ctx.agent_id,
            task_id=ctx.task_id,
            objective_id=ctx.objective_id,
            note=note,
        )
    except InvalidRequestError as e:
        raise ToolError(e.message, code="invalid_artifact") from e
    return {
        "artifact_id": w.artifact.id,
        "name": w.artifact.name,
        "version": w.artifact.version,
        "path": w.artifact.path,
        "created": w.created,
        "new_version": w.changed,
        "note": "identical to the latest version, nothing new stored" if not w.changed else "saved",
    }


async def create_document(ctx: ToolContext, a: CreateDocumentArgs) -> dict[str, Any]:
    return await _save(ctx, a.name, a.content, a.type, a.note)


async def create_markdown(ctx: ToolContext, a: CreateMarkdownArgs) -> dict[str, Any]:
    return await _save(ctx, a.name, a.content, "markdown", a.note)


TOOLS = [
    ToolDefinition(
        "create_document",
        "Save a finished deliverable as a versioned artifact (report, code, dataset, website…). "
        "Saving under an existing name adds a new version; nothing is overwritten.",
        CreateDocumentArgs,
        RiskLevel.MODERATE,
        create_document,
        permissions=frozenset({Capability.ARTIFACT_WRITE}),
        describe_impact=lambda a: f"Saves artifact {a.name} ({a.type}); earlier versions are kept.",
    ),
    ToolDefinition(
        "create_markdown",
        "Save a Markdown document as a versioned artifact.",
        CreateMarkdownArgs,
        RiskLevel.MODERATE,
        create_markdown,
        permissions=frozenset({Capability.ARTIFACT_WRITE}),
        describe_impact=lambda a: f"Saves Markdown artifact {a.name}; earlier versions are kept.",
    ),
]

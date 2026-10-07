from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container
from app.schemas.runtime import ArtifactContent, ArtifactOut, ArtifactVersionOut

router = APIRouter(prefix="/api", tags=["artifacts"])


@router.get("/projects/{project_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(project_id: str, c: Container, type_filter: str | None = None) -> list[ArtifactOut]:
    await c.projects.get(project_id)
    return await c.artifacts.list_artifacts(project_id=project_id, type_=type_filter)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(artifact_id: str, c: Container) -> ArtifactOut:
    return await c.artifacts.get(artifact_id)


@router.get("/artifacts/{artifact_id}/versions", response_model=list[ArtifactVersionOut])
async def artifact_versions(artifact_id: str, c: Container) -> list[ArtifactVersionOut]:
    return await c.artifacts.versions(artifact_id)


@router.get("/artifacts/{artifact_id}/content", response_model=ArtifactContent)
async def artifact_content(artifact_id: str, c: Container, version: int | None = None) -> ArtifactContent:
    artifact, number, text, truncated = await c.artifacts.read(artifact_id, version)
    return ArtifactContent(artifact=artifact, version=number, content=text, truncated=truncated)

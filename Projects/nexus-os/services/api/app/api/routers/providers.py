from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Container
from app.schemas.providers import (
    ConnectionTestOut,
    ModelOut,
    ProviderCreate,
    ProviderKindInfo,
    ProviderOut,
    ProviderUpdate,
)

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers/kinds", response_model=list[ProviderKindInfo])
async def provider_kinds(c: Container) -> list[ProviderKindInfo]:
    return c.providers.kinds()


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(c: Container) -> list[ProviderOut]:
    return await c.providers.list_all()


@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderCreate, c: Container) -> ProviderOut:
    return await c.providers.create(body)


@router.get("/providers/{provider_id}", response_model=ProviderOut)
async def get_provider(provider_id: str, c: Container) -> ProviderOut:
    return await c.providers.get(provider_id)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderUpdate, c: Container) -> ProviderOut:
    return await c.providers.update(provider_id, body)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: str, c: Container) -> Response:
    await c.providers.delete(provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/providers/{provider_id}/test", response_model=ConnectionTestOut)
async def test_provider(provider_id: str, c: Container) -> ConnectionTestOut:
    return await c.providers.test(provider_id)


@router.get("/providers/{provider_id}/models", response_model=list[ModelOut])
async def provider_models(provider_id: str, c: Container, refresh: bool = False) -> list[ModelOut]:
    return await c.providers.models(provider_id, refresh=refresh)


@router.get("/models", response_model=list[ModelOut])
async def all_models(c: Container) -> list[ModelOut]:
    return await c.providers.all_models()

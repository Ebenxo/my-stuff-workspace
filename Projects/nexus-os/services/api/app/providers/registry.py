"""Builds provider adapters from stored configuration and caches their model lists."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import httpx

from app.core.secrets import SecretStore
from app.models.database import Database
from app.models.foundation import ProviderConfiguration
from app.providers import catalog
from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider
from app.providers.errors import NoRouteError, ProviderError
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.scripted import ScriptedProvider
from app.providers.types import ModelInfo
from app.repositories.providers import ProviderRepository
from app.schemas.providers import ProviderOptions

MODEL_CACHE_TTL_S = 300.0

DemoFactory = Callable[[str], LLMProvider]


def new_http_client() -> httpx.AsyncClient:
    """Shared client for provider calls. Redirects are refused so API-key headers can never be
    replayed to another host by a hostile or misconfigured endpoint."""
    # Local model servers must never be routed through a system/corporate proxy, whatever NO_PROXY says.
    loopback = {f"all://{host}": httpx.AsyncHTTPTransport() for host in ("localhost", "127.0.0.1", "[::1]")}
    return httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        mounts=loopback,
    )


class ProviderRegistry:
    def __init__(
        self,
        db: Database,
        secrets: SecretStore,
        http: httpx.AsyncClient,
        *,
        demo_factory: DemoFactory | None = None,
    ) -> None:
        self._db = db
        self._secrets = secrets
        self._http = http
        self._demo_factory = demo_factory or (lambda pid: ScriptedProvider(pid))
        self._adapters: dict[str, tuple[object, LLMProvider]] = {}
        self._models: dict[str, tuple[float, list[ModelInfo]]] = {}

    async def configs(self, *, enabled_only: bool = False) -> list[ProviderConfiguration]:
        async with self._db.session() as session:
            return list(await ProviderRepository(session).list_all(enabled_only=enabled_only))

    async def config(self, provider_id: str) -> ProviderConfiguration:
        async with self._db.session() as session:
            row = await ProviderRepository(session).get(provider_id)
        if row is None:
            raise NoRouteError(f"Provider {provider_id} is not configured")
        return row

    def invalidate(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self._adapters.clear()
            self._models.clear()
        else:
            self._adapters.pop(provider_id, None)
            self._models.pop(provider_id, None)

    def invalidate_models(self, provider_id: str) -> None:
        self._models.pop(provider_id, None)

    async def _build(self, row: ProviderConfiguration) -> LLMProvider:
        key = await self._secrets.get(row.secret_ref) if row.secret_ref else None
        options = ProviderOptions.model_validate(row.options or {})
        kind = row.kind
        base_url = row.base_url or catalog.DEFAULT_BASE_URLS.get(kind)
        if kind == "anthropic":
            return AnthropicProvider(row.id, self._http, api_key=key, base_url=base_url)
        if kind in ("openai", "lmstudio", "openai_compatible"):
            return OpenAICompatProvider(
                row.id,
                self._http,
                kind=kind,
                api_key=key,
                base_url=base_url,
                structured_mode=options.structured_mode,
            )
        if kind == "ollama":
            return OllamaProvider(row.id, self._http, base_url=base_url, api_key=key)
        if kind == "gemini":
            return GeminiProvider(row.id, self._http, api_key=key, base_url=base_url)
        if kind == "demo":
            return self._demo_factory(row.id)
        raise NoRouteError(f"Unsupported provider kind: {kind}")

    async def get_provider(self, provider_id: str) -> LLMProvider:
        row = await self.config(provider_id)
        stamp = (row.updated_at, row.secret_ref, row.enabled)
        cached = self._adapters.get(provider_id)
        if cached and cached[0] == stamp:
            return cached[1]
        adapter = await self._build(row)
        self._adapters[provider_id] = (stamp, adapter)
        return adapter

    def enrich(self, row: ProviderConfiguration, models: list[ModelInfo]) -> list[ModelInfo]:
        options = ProviderOptions.model_validate(row.options or {})
        return [catalog.enrich(m, kind=row.kind, base_url=row.base_url, options=options) for m in models]

    async def models_for(self, provider_id: str, *, refresh: bool = False) -> list[ModelInfo]:
        """Discovered models (cached). On failure returns the cache, or just the default model."""
        row = await self.config(provider_id)
        cached = self._models.get(provider_id)
        if cached and not refresh and time.monotonic() - cached[0] < MODEL_CACHE_TTL_S:
            return cached[1]
        try:
            adapter = await self.get_provider(provider_id)
            found = await adapter.available_models()
        except ProviderError:
            if cached:
                return cached[1]
            found = []
        if row.default_model and all(m.id != row.default_model for m in found):
            found = [*found, ModelInfo(id=row.default_model, provider_id=row.id)]
        models = self.enrich(row, found)
        self._models[provider_id] = (time.monotonic(), models)
        return models

    async def model_info(self, provider_id: str, model: str) -> ModelInfo:
        """Enriched info for one model (falls back to heuristics when it was not discovered)."""
        for m in await self.models_for(provider_id):
            if m.id == model:
                return m
        row = await self.config(provider_id)
        return self.enrich(row, [ModelInfo(id=model, provider_id=provider_id)])[0]

    async def all_models(
        self, *, enabled_only: bool = True
    ) -> list[tuple[ProviderConfiguration, list[ModelInfo]]]:
        rows = await self.configs(enabled_only=enabled_only)
        lists = await asyncio.gather(*(self.models_for(r.id) for r in rows), return_exceptions=True)
        return [(r, m) for r, m in zip(rows, lists, strict=True) if not isinstance(m, BaseException)]

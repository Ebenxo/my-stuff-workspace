"""Provider configuration use cases. API keys are write-only: stored in the secret store, never returned."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.core.clock import Clock
from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.core.ids import new_id
from app.core.secrets import SecretStore
from app.core.security import mask_secret
from app.core.settings import Settings
from app.events.bus import EventBus
from app.events.types import EventType
from app.models.database import Database
from app.models.foundation import ProviderConfiguration
from app.providers import catalog
from app.providers.errors import NoRouteError
from app.providers.registry import ProviderRegistry
from app.providers.types import ConnectionTest, ModelInfo
from app.repositories.providers import ProviderRepository
from app.schemas.providers import (
    ConnectionTestOut,
    ModelOut,
    ProviderCreate,
    ProviderKindInfo,
    ProviderOptions,
    ProviderOut,
    ProviderUpdate,
)

log = logging.getLogger(__name__)

KINDS: list[ProviderKindInfo] = [
    ProviderKindInfo(
        kind="anthropic",
        label="Anthropic",
        default_base_url=catalog.DEFAULT_BASE_URLS["anthropic"],
        needs_key=True,
        local=False,
        help="Claude models via the Anthropic API.",
    ),
    ProviderKindInfo(
        kind="openai",
        label="OpenAI",
        default_base_url=catalog.DEFAULT_BASE_URLS["openai"],
        needs_key=True,
        local=False,
        help="GPT models via the OpenAI API.",
    ),
    ProviderKindInfo(
        kind="gemini",
        label="Google Gemini",
        default_base_url=catalog.DEFAULT_BASE_URLS["gemini"],
        needs_key=True,
        local=False,
        help="Gemini models via the Google AI API.",
    ),
    ProviderKindInfo(
        kind="ollama",
        label="Ollama (local)",
        default_base_url=catalog.DEFAULT_BASE_URLS["ollama"],
        needs_key=False,
        local=True,
        help="Models running on this machine through Ollama. Nothing leaves your computer.",
    ),
    ProviderKindInfo(
        kind="lmstudio",
        label="LM Studio (local)",
        default_base_url=catalog.DEFAULT_BASE_URLS["lmstudio"],
        needs_key=False,
        local=True,
        help="Models running on this machine through LM Studio's local server.",
    ),
    ProviderKindInfo(
        kind="openai_compatible",
        label="Custom OpenAI-compatible",
        default_base_url=None,
        needs_key=False,
        local=False,
        help="Any endpoint that speaks the OpenAI chat API (vLLM, OpenRouter, a company gateway…).",
    ),
]
_KIND = {k.kind: k for k in KINDS}
_DEMO = ProviderKindInfo(
    kind="demo",
    label="Demo (scripted)",
    default_base_url=None,
    needs_key=False,
    local=True,
    help="Scripted responses for the built-in demo. Not a real model.",
)


def validate_base_url(url: str, *, has_key: bool) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidRequestError("The base URL must start with http:// or https:// and include a host.")
    if parsed.username or parsed.password:
        raise InvalidRequestError("Do not put credentials in the URL; use the API key field.")
    if parsed.query or parsed.fragment:
        raise InvalidRequestError("The base URL must not contain a query string or fragment.")
    if parsed.scheme == "http" and has_key and not catalog.is_loopback_url(url):
        raise InvalidRequestError("An API key would be sent unencrypted. Use https:// for remote endpoints.")
    return url.strip().rstrip("/")


class ProviderService:
    def __init__(
        self,
        db: Database,
        bus: EventBus,
        secrets: SecretStore,
        registry: ProviderRegistry,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._db = db
        self._bus = bus
        self._secrets = secrets
        self._registry = registry
        self._clock = clock
        self._settings = settings

    def kinds(self) -> list[ProviderKindInfo]:
        return [*KINDS, _DEMO] if self._settings.enable_demo_provider else list(KINDS)

    async def _to_out(self, row: ProviderConfiguration) -> ProviderOut:
        key = await self._secrets.get(row.secret_ref) if row.secret_ref else None
        return ProviderOut(
            id=row.id,
            kind=row.kind,
            name=row.name,
            base_url=row.base_url,
            default_model=row.default_model,
            enabled=row.enabled,
            options=ProviderOptions.model_validate(row.options or {}),
            has_key=bool(key),
            key_hint=mask_secret(key) if key else None,
            is_local=catalog.is_local_provider(row.kind, row.base_url),
            last_test_at=row.last_test_at,
            last_test_ok=row.last_test_ok,
            last_test_error=row.last_test_error,
            created_at=row.created_at,
        )

    async def list_all(self) -> list[ProviderOut]:
        return [await self._to_out(r) for r in await self._registry.configs()]

    async def get(self, provider_id: str) -> ProviderOut:
        async with self._db.session() as session:
            row = await ProviderRepository(session).get(provider_id)
            if row is None:
                raise NotFoundError(f"Provider {provider_id} not found")
        return await self._to_out(row)

    async def create(self, data: ProviderCreate) -> ProviderOut:
        if data.kind == "demo":
            if not self._settings.enable_demo_provider:
                raise InvalidRequestError("The demo provider is disabled.")
        else:
            info = _KIND[data.kind]
            key_given = bool(data.api_key and data.api_key.strip())
            if info.needs_key and not key_given:
                raise InvalidRequestError(f"{info.label} needs an API key.")
            if data.kind == "openai_compatible" and not data.base_url:
                raise InvalidRequestError("A custom endpoint needs a base URL.")
        base_url = None
        if data.base_url:
            base_url = validate_base_url(data.base_url, has_key=bool(data.api_key and data.api_key.strip()))
        provider_id = new_id("prov")
        secret_ref: str | None = None
        if data.api_key and data.api_key.strip():
            secret_ref = f"provider:{provider_id}"
            await self._secrets.set(secret_ref, data.api_key.strip())
        now = self._clock.now()
        try:
            async with self._db.session() as session:
                row = await ProviderRepository(session).add(
                    ProviderConfiguration(
                        id=provider_id,
                        kind=data.kind,
                        name=data.name,
                        base_url=base_url,
                        default_model=(data.default_model or None),
                        enabled=data.enabled,
                        options=data.options.model_dump(mode="json"),
                        secret_ref=secret_ref,
                        created_at=now,
                        updated_at=now,
                    )
                )
                out_row = row
        except Exception:
            if secret_ref:
                await self._secrets.delete(secret_ref)  # do not orphan a key if the row was not saved
            raise
        await self._bus.emit(
            EventType.PROVIDER_CONFIGURED,
            actor="user",
            payload={
                "provider_id": provider_id,
                "kind": data.kind,
                "name": data.name,
                "has_key": secret_ref is not None,
            },
        )
        return await self._to_out(out_row)

    async def update(self, provider_id: str, patch: ProviderUpdate) -> ProviderOut:
        changes = patch.model_dump(exclude_unset=True)
        changed: list[str] = []
        new_key: str | None = None
        remove_key = False
        async with self._db.session() as session:
            row = await ProviderRepository(session).get(provider_id)
            if row is None:
                raise NotFoundError(f"Provider {provider_id} not found")
            if "api_key" in changes and changes["api_key"] is not None:
                if changes["api_key"].strip() == "":
                    remove_key = True
                else:
                    new_key = changes["api_key"].strip()
            has_key_after = bool(new_key) or (bool(row.secret_ref) and not remove_key)
            if "base_url" in changes:
                raw = changes["base_url"]
                row.base_url = validate_base_url(raw, has_key=has_key_after) if raw else None
                changed.append("base_url")
            elif new_key and row.base_url:
                validate_base_url(row.base_url, has_key=True)  # rotating in a key must not enable cleartext
            for key in ("name", "default_model", "enabled"):
                if key in changes and changes[key] is not None:
                    setattr(row, key, changes[key])
                    changed.append(key)
            if patch.options is not None:
                row.options = patch.options.model_dump(mode="json")
                changed.append("options")
            if new_key:
                row.secret_ref = f"provider:{provider_id}"
                changed.append("api_key")
            elif remove_key:
                row.secret_ref = None
                changed.append("api_key")
            row.updated_at = self._clock.now()
            secret_ref = f"provider:{provider_id}"
        if new_key:
            await self._secrets.set(secret_ref, new_key)
        elif remove_key:
            await self._secrets.delete(secret_ref)
        self._registry.invalidate(provider_id)
        await self._bus.emit(
            EventType.PROVIDER_CONFIGURED,
            actor="user",
            payload={"provider_id": provider_id, "changed": sorted(changed)},
        )
        return await self.get(provider_id)

    async def delete(self, provider_id: str) -> None:
        async with self._db.session() as session:
            repo = ProviderRepository(session)
            row = await repo.get(provider_id)
            if row is None:
                raise NotFoundError(f"Provider {provider_id} not found")
            secret_ref, name = row.secret_ref, row.name
            await repo.delete(row)
        if secret_ref:
            await self._secrets.delete(secret_ref)
        self._registry.invalidate(provider_id)
        await self._bus.emit(
            EventType.PROVIDER_REMOVED, actor="user", payload={"provider_id": provider_id, "name": name}
        )

    async def test(self, provider_id: str) -> ConnectionTestOut:
        try:
            adapter = await self._registry.get_provider(provider_id)
        except NoRouteError as exc:
            raise NotFoundError(f"Provider {provider_id} not found") from exc
        result: ConnectionTest = await adapter.test_connection()
        async with self._db.session() as session:
            row = await ProviderRepository(session).get(provider_id)
            if row is None:
                raise ConflictError("Provider was removed while testing")
            row.last_test_at = self._clock.now()
            row.last_test_ok = result.ok
            row.last_test_error = None if result.ok else result.detail[:500]
        self._registry.invalidate_models(provider_id)
        await self._bus.emit(
            EventType.PROVIDER_TESTED,
            actor="user",
            payload={
                "provider_id": provider_id,
                "ok": result.ok,
                "latency_ms": result.latency_ms,
                "error_code": result.error_code,
            },
        )
        return ConnectionTestOut(**result.model_dump())

    def _model_out(self, row: ProviderConfiguration, m: ModelInfo) -> ModelOut:
        return ModelOut(
            ref=f"{row.id}:{m.id}",
            provider_id=row.id,
            provider_name=row.name,
            id=m.id,
            display_name=m.display_name,
            context_length=m.context_length,
            tier=m.tier,
            local=m.local,
            input_cost_per_mtok=m.input_cost_per_mtok,
            output_cost_per_mtok=m.output_cost_per_mtok,
        )

    async def models(self, provider_id: str, *, refresh: bool = False) -> list[ModelOut]:
        try:
            row = await self._registry.config(provider_id)
        except NoRouteError as exc:
            raise NotFoundError(f"Provider {provider_id} not found") from exc
        return [
            self._model_out(row, m) for m in await self._registry.models_for(provider_id, refresh=refresh)
        ]

    async def all_models(self) -> list[ModelOut]:
        return [self._model_out(row, m) for row, models in await self._registry.all_models() for m in models]

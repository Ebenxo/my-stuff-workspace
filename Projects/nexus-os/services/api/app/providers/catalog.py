"""Model metadata: heuristics plus user overrides. Prices are never guessed.

Ships no price table: prices change and cannot be verified offline. ``input_cost_per_mtok`` is
None (unknown) unless the user sets one for a model, or the provider is local (free).
"""

from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlparse

from app.providers.types import ModelInfo
from app.schemas.providers import ModelOverride, ProviderOptions

Tier = Literal["fast", "balanced", "strong"]

_FAST = (
    "haiku",
    "mini",
    "nano",
    "flash",
    "lite",
    "small",
    "tiny",
    "instant",
    "-1b",
    "-3b",
    "-7b",
    "-8b",
    ":1b",
    ":3b",
    ":7b",
    ":8b",
)
_STRONG = (
    "opus",
    "fable",
    "ultra",
    "pro",
    "large",
    "reason",
    "thinking",
    "-70b",
    "-72b",
    "-120b",
    "-405b",
    ":70b",
    ":72b",
    ":120b",
    ":405b",
)
_STRONG_PREFIXES = ("o1", "o3", "o4")

LOCAL_KINDS = frozenset({"ollama", "lmstudio", "demo"})

# Where each kind lives when the user does not override it. One table, used by both the adapters
# (which must really call these) and the settings UI (which displays them).
DEFAULT_BASE_URLS: dict[str, str | None] = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com",
    "ollama": "http://127.0.0.1:11434",
    "lmstudio": "http://127.0.0.1:1234/v1",
    "openai_compatible": None,
    "demo": None,
}


def infer_tier(model_id: str) -> Tier:
    """Heuristic size/capability tier from the model name. Users can override per model."""
    m = model_id.lower()
    if any(m.startswith(p) for p in _STRONG_PREFIXES) or any(t in m for t in _STRONG):
        return "strong"
    if any(t in m for t in _FAST):
        return "fast"
    return "balanced"


def is_loopback_url(base_url: str | None) -> bool:
    if not base_url:
        return False
    host = urlparse(base_url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_local_provider(kind: str, base_url: str | None) -> bool:
    """Local means the model runs on this machine: Ollama/LM Studio kinds or a loopback endpoint."""
    return kind in LOCAL_KINDS or is_loopback_url(base_url)


def enrich(info: ModelInfo, *, kind: str, base_url: str | None, options: ProviderOptions | None) -> ModelInfo:
    """Apply heuristics and the user's per-model overrides to a discovered model."""
    override: ModelOverride | None = options.models.get(info.id) if options else None
    local = is_local_provider(kind, base_url)
    updates: dict[str, object] = {"local": local, "tier": info.tier or infer_tier(info.id)}
    if local:
        updates["input_cost_per_mtok"] = 0.0
        updates["output_cost_per_mtok"] = 0.0
    if override:
        if override.context_length is not None:
            updates["context_length"] = override.context_length
        if override.tier is not None:
            updates["tier"] = override.tier
        if override.supports_vision is not None:
            updates["supports_vision"] = override.supports_vision
        if override.supports_reasoning is not None:
            updates["supports_reasoning"] = override.supports_reasoning
        if override.price is not None:
            updates["input_cost_per_mtok"] = override.price.input
            updates["output_cost_per_mtok"] = override.price.output
    return info.model_copy(update=updates)


def cost_usd(input_tokens: int, output_tokens: int, info: ModelInfo | None) -> float | None:
    """Cost in USD, or None when the price is unknown."""
    if info is None or info.input_cost_per_mtok is None or info.output_cost_per_mtok is None:
        return None
    return (input_tokens * info.input_cost_per_mtok + output_tokens * info.output_cost_per_mtok) / 1_000_000

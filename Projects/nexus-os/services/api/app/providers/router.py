"""Model routing: choose a primary model and fallbacks for a call.

Precedence: manual override > the agent's preferred model > the user's routing rules > the built-in
policy for the task class. A *private* task can only ever use local models; if there are none the
router refuses rather than silently sending private data to a cloud provider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.providers.errors import NoRouteError
from app.providers.registry import ProviderRegistry
from app.providers.types import ModelInfo
from app.schemas.providers import RoutingRule, RoutingRules

MAX_FALLBACKS = 4
TIER_ORDER = {"fast": 0, "balanced": 1, "strong": 2}


class TaskClass(StrEnum):
    FORMATTING = "formatting"
    CODING = "coding"
    PLANNING = "planning"
    LONG_DOCUMENT = "long_document"
    GENERAL = "general"


# Built-in policy: which tier suits which class of work.
DEFAULT_TIER: dict[TaskClass, str] = {
    TaskClass.FORMATTING: "fast",
    TaskClass.CODING: "strong",
    TaskClass.PLANNING: "strong",
    TaskClass.LONG_DOCUMENT: "strong",
    TaskClass.GENERAL: "balanced",
}


@dataclass(frozen=True)
class ModelRef:
    provider_id: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider_id}:{self.model}"

    @staticmethod
    def parse(raw: str) -> ModelRef:
        # Model ids may contain ':' (e.g. Ollama "llama3:8b"), so split on the first one only.
        provider_id, sep, model = raw.partition(":")
        if not sep or not provider_id or not model:
            raise ValueError(f"model reference must look like '<provider_id>:<model>', got {raw!r}")
        return ModelRef(provider_id, model)


@dataclass(frozen=True)
class RouteRequest:
    task_class: TaskClass = TaskClass.GENERAL
    private: bool = False
    input_tokens: int = 0
    needs_vision: bool = False
    preferred: str | None = None
    fallbacks: list[str] = field(default_factory=list)
    manual_override: str | None = None


@dataclass(frozen=True)
class Route:
    primary: ModelRef
    fallbacks: list[ModelRef]
    reason: str


@dataclass(frozen=True)
class Candidate:
    ref: ModelRef
    info: ModelInfo
    order: int  # provider creation order, for stable tie-breaks
    default: bool  # this is the provider's configured default model


RulesProvider = Callable[[], Awaitable[RoutingRules]]


class ModelRouter:
    def __init__(self, registry: ProviderRegistry, rules: RulesProvider) -> None:
        self._registry = registry
        self._rules = rules

    async def _candidates(self) -> list[Candidate]:
        out: list[Candidate] = []
        for order, (row, models) in enumerate(await self._registry.all_models(enabled_only=True)):
            for m in models:
                out.append(Candidate(ModelRef(row.id, m.id), m, order, m.id == row.default_model))
        return out

    @staticmethod
    def _sorted(cands: list[Candidate]) -> list[Candidate]:
        # Stable, explainable ordering: the provider's default model first, then provider order, then id.
        return sorted(cands, key=lambda c: (not c.default, c.order, c.ref.model))

    @staticmethod
    def _by_tier(cands: list[Candidate], tier: str) -> list[Candidate]:
        """Candidates of the wanted tier; if none, those of the nearest tier (stronger wins a tie)."""
        want = TIER_ORDER[tier]

        def rank(c: Candidate) -> tuple[int, int]:
            t = TIER_ORDER.get(c.info.tier or "balanced", 1)
            return (abs(t - want), -t)

        best = min(rank(c) for c in cands)
        return [c for c in cands if rank(c) == best]

    @staticmethod
    def _find(cands: list[Candidate], raw: str | None) -> Candidate | None:
        if not raw:
            return None
        try:
            ref = ModelRef.parse(raw)
        except ValueError:
            return None
        return next((c for c in cands if c.ref == ref), None)

    def _apply_rule(self, rule: RoutingRule, cands: list[Candidate]) -> Candidate | None:
        pref = rule.prefer
        if pref.model:
            return self._find(cands, pref.model)
        pool = cands
        if pref.provider_id:
            pool = [c for c in pool if c.ref.provider_id == pref.provider_id]
        if pref.local is not None:
            pool = [c for c in pool if c.info.local == pref.local]
        if not pool:
            return None
        if pref.tier:
            pool = self._by_tier(pool, pref.tier)
        return self._sorted(pool)[0]

    @staticmethod
    def _rule_matches(rule: RoutingRule, rr: RouteRequest) -> bool:
        w = rule.when
        if w.task_class is not None and w.task_class != rr.task_class.value:
            return False
        if w.private is not None and w.private != rr.private:
            return False
        return not (w.min_input_tokens is not None and rr.input_tokens < w.min_input_tokens)

    async def route(self, rr: RouteRequest) -> Route:
        all_cands = await self._candidates()
        if not all_cands:
            raise NoRouteError("No AI provider is ready. Add one in Settings → AI Providers.")

        cands = all_cands
        if rr.private:
            cands = [c for c in cands if c.info.local]
            if not cands:
                raise NoRouteError(
                    "This task is private, but no local model is available. "
                    "Add an Ollama or LM Studio provider, or mark the task as not private."
                )
        if rr.input_tokens:
            need = int(rr.input_tokens * 1.1)
            fitting = [c for c in cands if c.info.context_length is None or c.info.context_length >= need]
            cands = fitting or cands  # if nothing is known to fit, let the provider report the overflow
        if rr.needs_vision:
            cands = [c for c in cands if c.info.supports_vision is not False] or cands

        primary: Candidate | None = None
        reason = ""

        if rr.manual_override:
            primary = self._find(cands, rr.manual_override)
            if primary is None:
                if self._find(all_cands, rr.manual_override) is not None and rr.private:
                    raise NoRouteError("The chosen model is not local, and this task is private.")
                raise NoRouteError(f"The chosen model {rr.manual_override} is not available.")
            reason = "manual override"
        if primary is None and rr.preferred:
            primary = self._find(cands, rr.preferred)
            if primary is not None:
                reason = "agent preference"
        if primary is None:
            for rule in (await self._rules()).rules:
                if self._rule_matches(rule, rr):
                    picked = self._apply_rule(rule, cands)
                    if picked is not None:
                        primary, reason = picked, f"routing rule “{rule.name}”"
                        break
        if primary is None:
            if rr.task_class is TaskClass.LONG_DOCUMENT:
                known = [c for c in cands if c.info.context_length]
                if known:
                    primary = self._sorted([max(known, key=lambda c: c.info.context_length or 0)])[0]
                    reason = "largest known context window for a long document"
            if primary is None:
                tier = DEFAULT_TIER[rr.task_class]
                primary = self._sorted(self._by_tier(cands, tier))[0]
                reason = f"default policy: {rr.task_class.value} → {tier} tier"
        if rr.private:
            reason += " (private: local models only)"

        fallbacks: list[ModelRef] = []

        def add(c: Candidate | None) -> None:
            if c and c.ref != primary.ref and c.ref not in fallbacks and len(fallbacks) < MAX_FALLBACKS:
                fallbacks.append(c.ref)

        for raw in rr.fallbacks:
            add(self._find(cands, raw))
        defaults_first = [c for c in self._sorted(cands) if c.default]
        for c in defaults_first:
            add(c)
        return Route(primary.ref, fallbacks, reason)

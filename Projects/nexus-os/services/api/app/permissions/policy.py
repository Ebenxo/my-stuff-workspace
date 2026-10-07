"""The policy engine: a pure function from (tool, arguments' risk, agent, project policy, run state)
to ALLOW / REQUIRE_APPROVAL / DENY. No model output, and no text of any kind, is an input.

    cautious   : SAFE auto; everything else asks
    balanced   : SAFE and MODERATE auto; HIGH and above ask
    permissive : up to HIGH auto, unless the tool always asks or the run has read untrusted content
    all levels : VERY_HIGH always asks; always-ask tools always ask; unattended runs never auto-run HIGH
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.risk import RiskLevel, max_risk
from app.schemas.common import PermissionLevel


class Verdict(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class RiskAssessment:
    """What a tool says about *these particular arguments*. May raise risk, demand approval or deny."""

    level: RiskLevel = RiskLevel.SAFE
    deny_reason: str | None = None
    always_ask: bool = False
    impact: str = ""


@dataclass(frozen=True)
class PolicyInput:
    tool_name: str
    static_risk: RiskLevel
    tool_always_asks: bool
    assessment: RiskAssessment
    permission_level: PermissionLevel
    agent_max_risk: RiskLevel
    agent_may_request_approval: bool
    unattended: bool = False
    tainted: bool = False
    session_granted: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    effective_risk: RiskLevel
    reasons: list[str] = field(default_factory=list)
    session_grantable: bool = False
    always_ask: bool = False


_CEILING = {
    PermissionLevel.CAUTIOUS: RiskLevel.SAFE,
    PermissionLevel.BALANCED: RiskLevel.MODERATE,
    PermissionLevel.PERMISSIVE: RiskLevel.HIGH,
}


def evaluate(p: PolicyInput) -> PolicyDecision:
    eff = max_risk(p.static_risk, p.assessment.level)

    if p.assessment.deny_reason:
        return PolicyDecision(Verdict.DENY, eff, [p.assessment.deny_reason])
    if eff > p.agent_max_risk:
        return PolicyDecision(
            Verdict.DENY,
            eff,
            [f"{p.tool_name} is {eff.value} risk, beyond this agent's limit ({p.agent_max_risk.value})."],
        )

    always = p.tool_always_asks or p.assessment.always_ask or eff is RiskLevel.VERY_HIGH
    grantable = eff <= RiskLevel.HIGH and not always

    ceiling = _CEILING[p.permission_level]
    reasons: list[str] = []
    if p.permission_level is PermissionLevel.PERMISSIVE and p.tainted:
        ceiling = RiskLevel.MODERATE
        reasons.append("this run has read untrusted content, so higher-risk actions are not auto-approved")
    if p.unattended and ceiling > RiskLevel.MODERATE:
        ceiling = RiskLevel.MODERATE
        reasons.append("unattended runs never auto-approve high-risk actions")

    if not always and eff <= ceiling:
        return PolicyDecision(
            Verdict.ALLOW, eff, ["within the project's permission level"], grantable, always
        )

    if always:
        reasons.append("this action always needs approval")
    else:
        reasons.append(f"{eff.value} risk needs approval at the '{p.permission_level.value}' level")

    if grantable and p.session_granted and not p.tainted and not p.unattended:
        return PolicyDecision(Verdict.ALLOW, eff, ["approved earlier for this session"], grantable, always)

    if not p.agent_may_request_approval:
        return PolicyDecision(
            Verdict.DENY, eff, [*reasons, "this agent may not request approval"], grantable, always
        )
    return PolicyDecision(Verdict.REQUIRE_APPROVAL, eff, reasons, grantable, always)

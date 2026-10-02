from __future__ import annotations

import itertools

import pytest

from app.core.risk import RiskLevel, max_risk
from app.permissions.policy import PolicyInput, RiskAssessment, Verdict, evaluate
from app.schemas.common import PermissionLevel

R = RiskLevel
L = PermissionLevel


def make(
    *,
    static: RiskLevel = R.SAFE,
    dyn: RiskLevel = R.SAFE,
    level: PermissionLevel = L.BALANCED,
    agent_max: RiskLevel = R.VERY_HIGH,
    may_ask: bool = True,
    always_tool: bool = False,
    always_args: bool = False,
    deny: str | None = None,
    unattended: bool = False,
    tainted: bool = False,
    granted: bool = False,
) -> PolicyInput:
    return PolicyInput(
        tool_name="t",
        static_risk=static,
        tool_always_asks=always_tool,
        assessment=RiskAssessment(level=dyn, deny_reason=deny, always_ask=always_args),
        permission_level=level,
        agent_max_risk=agent_max,
        agent_may_request_approval=may_ask,
        unattended=unattended,
        tainted=tainted,
        session_granted=granted,
    )


def test_risk_ordering() -> None:
    assert R.SAFE < R.MODERATE < R.HIGH < R.VERY_HIGH
    assert R.HIGH >= R.HIGH and not (R.HIGH < R.HIGH)
    assert max_risk(R.SAFE, R.HIGH, R.MODERATE) is R.HIGH
    assert sorted([R.VERY_HIGH, R.SAFE, R.HIGH, R.MODERATE]) == [R.SAFE, R.MODERATE, R.HIGH, R.VERY_HIGH]


# The documented matrix, written out by hand.
MATRIX = {
    (L.CAUTIOUS, R.SAFE): Verdict.ALLOW,
    (L.CAUTIOUS, R.MODERATE): Verdict.REQUIRE_APPROVAL,
    (L.CAUTIOUS, R.HIGH): Verdict.REQUIRE_APPROVAL,
    (L.CAUTIOUS, R.VERY_HIGH): Verdict.REQUIRE_APPROVAL,
    (L.BALANCED, R.SAFE): Verdict.ALLOW,
    (L.BALANCED, R.MODERATE): Verdict.ALLOW,
    (L.BALANCED, R.HIGH): Verdict.REQUIRE_APPROVAL,
    (L.BALANCED, R.VERY_HIGH): Verdict.REQUIRE_APPROVAL,
    (L.PERMISSIVE, R.SAFE): Verdict.ALLOW,
    (L.PERMISSIVE, R.MODERATE): Verdict.ALLOW,
    (L.PERMISSIVE, R.HIGH): Verdict.ALLOW,
    (L.PERMISSIVE, R.VERY_HIGH): Verdict.REQUIRE_APPROVAL,
}


@pytest.mark.parametrize(("level", "risk"), list(MATRIX))
def test_permission_level_matrix(level: PermissionLevel, risk: RiskLevel) -> None:
    assert evaluate(make(static=risk, level=level)).verdict is MATRIX[(level, risk)]


def test_dynamic_assessment_can_raise_but_never_lower_risk() -> None:
    d = evaluate(make(static=R.MODERATE, dyn=R.HIGH, level=L.BALANCED))
    assert d.effective_risk is R.HIGH and d.verdict is Verdict.REQUIRE_APPROVAL
    d = evaluate(make(static=R.HIGH, dyn=R.SAFE, level=L.BALANCED))
    assert d.effective_risk is R.HIGH  # a tool cannot argue its way down


def test_deny_assessment_is_final_at_every_level() -> None:
    for level in PermissionLevel:
        d = evaluate(make(static=R.SAFE, level=level, deny="path escapes the workspace", granted=True))
        assert d.verdict is Verdict.DENY and "escapes" in d.reasons[0]


def test_agent_risk_ceiling_denies_before_anyone_is_asked() -> None:
    d = evaluate(make(static=R.HIGH, agent_max=R.MODERATE))
    assert d.verdict is Verdict.DENY and "beyond this agent" in d.reasons[0]
    assert evaluate(make(static=R.MODERATE, agent_max=R.MODERATE)).verdict is Verdict.ALLOW
    assert (
        evaluate(make(static=R.SAFE, dyn=R.MODERATE, agent_max=R.SAFE)).verdict is Verdict.DENY
    )  # dynamic risk counts


def test_agent_that_may_not_ask_is_denied_instead_of_asking() -> None:
    d = evaluate(make(static=R.HIGH, may_ask=False))
    assert d.verdict is Verdict.DENY and "may not request approval" in d.reasons[-1]
    assert evaluate(make(static=R.SAFE, may_ask=False)).verdict is Verdict.ALLOW  # nothing to ask about


def test_always_ask_tools_ignore_permissive_and_session_grants() -> None:
    for tool_flag, args_flag in ((True, False), (False, True)):
        d = evaluate(
            make(
                static=R.HIGH, level=L.PERMISSIVE, always_tool=tool_flag, always_args=args_flag, granted=True
            )
        )
        assert d.verdict is Verdict.REQUIRE_APPROVAL and d.always_ask and not d.session_grantable
    # even a MODERATE always-ask action asks under permissive
    assert (
        evaluate(make(static=R.MODERATE, level=L.PERMISSIVE, always_tool=True)).verdict
        is Verdict.REQUIRE_APPROVAL
    )


def test_very_high_always_asks_and_is_never_session_grantable() -> None:
    d = evaluate(make(static=R.VERY_HIGH, level=L.PERMISSIVE, granted=True))
    assert d.verdict is Verdict.REQUIRE_APPROVAL and not d.session_grantable and d.always_ask


def test_session_grant_skips_the_prompt_only_for_grantable_actions() -> None:
    asked = evaluate(make(static=R.HIGH, level=L.BALANCED))
    assert asked.verdict is Verdict.REQUIRE_APPROVAL and asked.session_grantable
    granted = evaluate(make(static=R.HIGH, level=L.BALANCED, granted=True))
    assert granted.verdict is Verdict.ALLOW and "session" in granted.reasons[0]
    cautious = evaluate(make(static=R.MODERATE, level=L.CAUTIOUS, granted=True))
    assert cautious.verdict is Verdict.ALLOW  # 'approve for session' works at the cautious level too


def test_taint_disables_permissive_high_auto_approval_and_session_grants() -> None:
    assert evaluate(make(static=R.HIGH, level=L.PERMISSIVE)).verdict is Verdict.ALLOW
    tainted = evaluate(make(static=R.HIGH, level=L.PERMISSIVE, tainted=True))
    assert tainted.verdict is Verdict.REQUIRE_APPROVAL and any("untrusted" in r for r in tainted.reasons)
    # a session grant does not carry over into a tainted run
    assert (
        evaluate(make(static=R.HIGH, level=L.BALANCED, tainted=True, granted=True)).verdict
        is Verdict.REQUIRE_APPROVAL
    )
    # taint does not make harmless things ask
    assert evaluate(make(static=R.SAFE, level=L.PERMISSIVE, tainted=True)).verdict is Verdict.ALLOW
    assert evaluate(make(static=R.MODERATE, level=L.PERMISSIVE, tainted=True)).verdict is Verdict.ALLOW


def test_unattended_runs_never_auto_run_high_risk() -> None:
    d = evaluate(make(static=R.HIGH, level=L.PERMISSIVE, unattended=True))
    assert d.verdict is Verdict.REQUIRE_APPROVAL and any("unattended" in r for r in d.reasons)
    assert (
        evaluate(make(static=R.HIGH, level=L.BALANCED, unattended=True, granted=True)).verdict
        is Verdict.REQUIRE_APPROVAL
    )
    assert evaluate(make(static=R.MODERATE, level=L.BALANCED, unattended=True)).verdict is Verdict.ALLOW
    assert (
        evaluate(make(static=R.MODERATE, level=L.CAUTIOUS, unattended=True)).verdict
        is Verdict.REQUIRE_APPROVAL
    )


def test_invariants_over_every_combination() -> None:
    """No combination of flags can break the hard rules."""
    for static, dyn, level, may_ask, ta, aa, deny, unatt, taint, granted, agent_max in itertools.product(
        list(R),
        list(R),
        list(L),
        (True, False),
        (True, False),
        (True, False),
        (None, "no"),
        (True, False),
        (True, False),
        (True, False),
        list(R),
    ):
        d = evaluate(
            make(
                static=static,
                dyn=dyn,
                level=level,
                may_ask=may_ask,
                always_tool=ta,
                always_args=aa,
                deny=deny,
                unattended=unatt,
                tainted=taint,
                granted=granted,
                agent_max=agent_max,
            )
        )
        eff = max_risk(static, dyn)
        assert d.effective_risk is eff
        if deny:
            assert d.verdict is Verdict.DENY
        if eff > agent_max:
            assert d.verdict is Verdict.DENY
        if d.verdict is Verdict.ALLOW:
            assert not deny and eff <= agent_max
            assert eff is not R.VERY_HIGH, "VERY_HIGH must never run without a human"
            assert not (ta or aa), "always-ask actions must never run without a human"
            if level is L.CAUTIOUS and not granted:
                assert eff is R.SAFE
            if unatt:
                assert eff <= R.MODERATE, "unattended runs must never silently run HIGH"
            if taint and level is L.PERMISSIVE and not granted:
                assert eff <= R.MODERATE
        if d.verdict is Verdict.REQUIRE_APPROVAL:
            assert may_ask and not deny and eff <= agent_max
        if d.session_grantable:
            assert eff <= R.HIGH and not (ta or aa)

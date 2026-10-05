import pytest
from ceo.safety import (
    SafetyPolicy,
    SafetyDecision,
    evaluate_safety,
    SIDE_EFFECT_NONE,
    SIDE_EFFECT_CONTENT,
    SIDE_EFFECT_LISTING,
    SIDE_EFFECT_MARKETING,
    SIDE_EFFECT_PURCHASE,
    SIDE_EFFECT_FINANCIAL,
    ACTION_ECONOMIC_SPEND,
    ACTION_SIDE_EFFECT,
    DEFAULT_POLICY,
)


class TestSideEffectApproval:
    def test_no_side_effect_allowed(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=None)
        assert decision.allowed is True
        assert decision.requires_approval is False

    def test_none_side_effect_allowed(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_NONE)
        assert decision.requires_approval is False

    def test_content_side_effect_requires_approval(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_CONTENT)
        assert decision.requires_approval is True
        assert decision.action_type == ACTION_SIDE_EFFECT

    def test_listing_side_effect_requires_approval(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_LISTING)
        assert decision.requires_approval is True

    def test_marketing_side_effect_requires_approval(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_MARKETING)
        assert decision.requires_approval is True

    def test_purchase_side_effect_requires_approval(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_PURCHASE)
        assert decision.requires_approval is True

    def test_financial_side_effect_requires_approval(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_FINANCIAL)
        assert decision.requires_approval is True

    def test_side_effect_allowed_when_policy_disabled(self):
        policy = SafetyPolicy(require_approval_for_side_effects=False)
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_LISTING)
        assert decision.requires_approval is False

    def test_side_effect_in_allowed_set_no_approval(self):
        policy = SafetyPolicy(
            require_approval_for_side_effects=True,
            allowed_side_effects_without_approval={SIDE_EFFECT_NONE, SIDE_EFFECT_CONTENT},
        )
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_CONTENT)
        assert decision.requires_approval is False


class TestSpendingLimitApproval:
    def test_spend_within_limit_allowed(self):
        policy = SafetyPolicy(max_automated_spend=50.0)
        plan = {"spend": 30.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is False

    def test_spend_exceeds_limit_requires_approval(self):
        policy = SafetyPolicy(max_automated_spend=5.0)
        plan = {"spend": 20.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is True
        assert decision.action_type == ACTION_ECONOMIC_SPEND

    def test_spend_at_limit_allowed(self):
        policy = SafetyPolicy(max_automated_spend=10.0)
        plan = {"spend": 10.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is False

    def test_zero_max_spend_any_spend_requires_approval(self):
        policy = SafetyPolicy(max_automated_spend=0.0)
        plan = {"spend": 0.01}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is True

    def test_zero_spend_plan_allowed(self):
        policy = SafetyPolicy(max_automated_spend=0.0)
        plan = {"spend": 0.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is False

    def test_spend_takes_priority_over_side_effect(self):
        policy = SafetyPolicy(require_approval_for_side_effects=True, max_automated_spend=5.0)
        plan = {"spend": 20.0}
        decision = evaluate_safety(policy, side_effect_type=SIDE_EFFECT_LISTING, economic_plan=plan)
        assert decision.action_type == ACTION_ECONOMIC_SPEND

    def test_default_policy_any_spend_requires_approval(self):
        plan = {"spend": 1.0}
        decision = evaluate_safety(DEFAULT_POLICY, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is True

    def test_spend_recorded_in_decision(self):
        policy = SafetyPolicy(max_automated_spend=5.0)
        plan = {"spend": 20.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.spend_requested == 20.0

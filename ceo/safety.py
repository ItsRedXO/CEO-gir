from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

SIDE_EFFECT_NONE = "none"
SIDE_EFFECT_CONTENT = "content"
SIDE_EFFECT_LISTING = "listing"
SIDE_EFFECT_MARKETING = "marketing"
SIDE_EFFECT_PURCHASE = "purchase"
SIDE_EFFECT_FINANCIAL = "financial"

SIDE_EFFECT_TYPES = {
    SIDE_EFFECT_NONE,
    SIDE_EFFECT_CONTENT,
    SIDE_EFFECT_LISTING,
    SIDE_EFFECT_MARKETING,
    SIDE_EFFECT_PURCHASE,
    SIDE_EFFECT_FINANCIAL,
}

ACTION_ECONOMIC_SPEND = "economic_spend"
ACTION_SIDE_EFFECT = "side_effect"


@dataclass
class SafetyPolicy:
    require_approval_for_side_effects: bool = True
    max_automated_spend: float = 0.0
    allowed_side_effects_without_approval: set = field(default_factory=lambda: {SIDE_EFFECT_NONE})


@dataclass
class SafetyDecision:
    allowed: bool
    requires_approval: bool
    reason: str
    action_type: Optional[str] = None
    spend_requested: float = 0.0


def evaluate_safety(
    policy: SafetyPolicy,
    side_effect_type: Optional[str],
    economic_plan: Optional[dict] = None,
) -> SafetyDecision:
    planned_spend = 0.0
    if economic_plan:
        planned_spend = float(economic_plan.get("spend", 0.0))

    # Check economic spend limit first
    if planned_spend > policy.max_automated_spend:
        return SafetyDecision(
            allowed=True,
            requires_approval=True,
            reason=f"planned spend ${planned_spend:.2f} exceeds automated limit ${policy.max_automated_spend:.2f}",
            action_type=ACTION_ECONOMIC_SPEND,
            spend_requested=planned_spend,
        )

    # Check side-effect approval requirement
    if side_effect_type and side_effect_type != SIDE_EFFECT_NONE:
        if policy.require_approval_for_side_effects:
            if side_effect_type not in policy.allowed_side_effects_without_approval:
                return SafetyDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"side_effect_type '{side_effect_type}' requires human approval",
                    action_type=ACTION_SIDE_EFFECT,
                    spend_requested=planned_spend,
                )

    return SafetyDecision(
        allowed=True,
        requires_approval=False,
        reason="within policy",
        spend_requested=planned_spend,
    )


DEFAULT_POLICY = SafetyPolicy(
    require_approval_for_side_effects=True,
    max_automated_spend=0.0,
)

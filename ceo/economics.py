from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class EconomicOutcome:
    revenue: float
    spend: float
    fees: float
    profit: float
    roi: Optional[float]
    roas: Optional[float]
    currency: str = "USD"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EconomicOutcome":
        return cls(
            revenue=d["revenue"],
            spend=d["spend"],
            fees=d["fees"],
            profit=d["profit"],
            roi=d.get("roi"),
            roas=d.get("roas"),
            currency=d.get("currency", "USD"),
        )


def calculate_economic_outcome(
    revenue: float,
    spend: float,
    fees: float = 0.0,
    currency: str = "USD",
) -> EconomicOutcome:
    if revenue < 0:
        raise ValueError(f"revenue cannot be negative: {revenue}")
    if spend < 0:
        raise ValueError(f"spend cannot be negative: {spend}")
    if fees < 0:
        raise ValueError(f"fees cannot be negative: {fees}")

    profit = revenue - spend - fees
    cost = spend + fees

    roi: Optional[float] = None
    roas: Optional[float] = None

    if cost > 0:
        roi = profit / cost
    if spend > 0:
        roas = revenue / spend

    return EconomicOutcome(
        revenue=revenue,
        spend=spend,
        fees=fees,
        profit=profit,
        roi=roi,
        roas=roas,
        currency=currency,
    )


def extract_economic_plan(input_data: dict) -> Optional[dict]:
    """Pull the economic_plan block out of task input_json."""
    if not isinstance(input_data, dict):
        return None
    return input_data.get("economic_plan")


def validate_economic_plan(plan: dict) -> None:
    if plan.get("spend", 0) < 0:
        raise ValueError("planned spend cannot be negative")
    if plan.get("revenue_estimate", 0) < 0:
        raise ValueError("planned revenue estimate cannot be negative")
    if plan.get("fees", 0) < 0:
        raise ValueError("planned fees cannot be negative")

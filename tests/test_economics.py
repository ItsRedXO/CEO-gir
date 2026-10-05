import pytest
from ceo.economics import (
    EconomicOutcome,
    calculate_economic_outcome,
    extract_economic_plan,
    validate_economic_plan,
)


class TestProfitCalculation:
    def test_basic_profit(self):
        o = calculate_economic_outcome(revenue=100, spend=60, fees=10)
        assert o.profit == 30.0

    def test_zero_profit(self):
        o = calculate_economic_outcome(revenue=50, spend=40, fees=10)
        assert o.profit == 0.0

    def test_negative_profit(self):
        o = calculate_economic_outcome(revenue=20, spend=30, fees=5)
        assert o.profit == -15.0

    def test_zero_cost(self):
        o = calculate_economic_outcome(revenue=50, spend=0, fees=0)
        assert o.profit == 50.0

    def test_fees_included_in_profit(self):
        o = calculate_economic_outcome(revenue=100, spend=50, fees=20)
        assert o.profit == 30.0

    def test_currency_default(self):
        o = calculate_economic_outcome(revenue=10, spend=5)
        assert o.currency == "USD"

    def test_currency_custom(self):
        o = calculate_economic_outcome(revenue=10, spend=5, currency="EUR")
        assert o.currency == "EUR"


class TestROICalculation:
    def test_positive_roi(self):
        o = calculate_economic_outcome(revenue=100, spend=40, fees=10)
        # profit=50, cost=50, roi=1.0
        assert o.roi == pytest.approx(1.0)

    def test_negative_roi(self):
        o = calculate_economic_outcome(revenue=10, spend=50, fees=5)
        # profit=-45, cost=55, roi=-45/55
        assert o.roi == pytest.approx(-45 / 55)

    def test_zero_cost_roi_is_none(self):
        o = calculate_economic_outcome(revenue=50, spend=0, fees=0)
        assert o.roi is None

    def test_roi_only_fees(self):
        o = calculate_economic_outcome(revenue=100, spend=0, fees=10)
        # profit=90, cost=10, roi=9.0
        assert o.roi == pytest.approx(9.0)


class TestROASCalculation:
    def test_positive_roas(self):
        o = calculate_economic_outcome(revenue=100, spend=25)
        assert o.roas == pytest.approx(4.0)

    def test_zero_spend_roas_is_none(self):
        o = calculate_economic_outcome(revenue=50, spend=0)
        assert o.roas is None

    def test_roas_below_one(self):
        o = calculate_economic_outcome(revenue=10, spend=50)
        assert o.roas == pytest.approx(0.2)


class TestNegativeValueRejection:
    def test_negative_revenue_rejected(self):
        with pytest.raises(ValueError, match="revenue"):
            calculate_economic_outcome(revenue=-1, spend=10)

    def test_negative_spend_rejected(self):
        with pytest.raises(ValueError, match="spend"):
            calculate_economic_outcome(revenue=10, spend=-1)

    def test_negative_fees_rejected(self):
        with pytest.raises(ValueError, match="fees"):
            calculate_economic_outcome(revenue=10, spend=5, fees=-1)


class TestSerialization:
    def test_to_dict_roundtrip(self):
        o = calculate_economic_outcome(revenue=80, spend=20, fees=5)
        d = o.to_dict()
        assert d["revenue"] == 80
        assert d["profit"] == 55
        assert "roi" in d
        assert "roas" in d

    def test_from_dict(self):
        d = {"revenue": 100, "spend": 40, "fees": 10, "profit": 50, "roi": 1.0, "roas": 2.5, "currency": "USD"}
        o = EconomicOutcome.from_dict(d)
        assert o.profit == 50
        assert o.roi == 1.0

    def test_from_dict_missing_roi_roas(self):
        d = {"revenue": 0, "spend": 0, "fees": 0, "profit": 0, "roi": None, "roas": None}
        o = EconomicOutcome.from_dict(d)
        assert o.roi is None
        assert o.roas is None


class TestExtractEconomicPlan:
    def test_extract_present(self):
        data = {"economic_plan": {"spend": 20, "currency": "USD"}}
        plan = extract_economic_plan(data)
        assert plan["spend"] == 20

    def test_extract_missing(self):
        data = {"other_key": "value"}
        assert extract_economic_plan(data) is None

    def test_extract_empty_dict(self):
        assert extract_economic_plan({}) is None

    def test_extract_non_dict(self):
        assert extract_economic_plan(None) is None
        assert extract_economic_plan("string") is None


class TestValidateEconomicPlan:
    def test_valid_plan(self):
        validate_economic_plan({"spend": 10, "revenue_estimate": 50})

    def test_negative_spend_rejected(self):
        with pytest.raises(ValueError):
            validate_economic_plan({"spend": -5})

    def test_negative_revenue_estimate_rejected(self):
        with pytest.raises(ValueError):
            validate_economic_plan({"revenue_estimate": -10})

    def test_negative_fees_rejected(self):
        with pytest.raises(ValueError):
            validate_economic_plan({"fees": -1})

    def test_zero_values_ok(self):
        validate_economic_plan({"spend": 0, "fees": 0})

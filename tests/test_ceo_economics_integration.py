"""
Integration tests for economics + safety + orchestration.
These verify the full lifecycle of economic tasks through the approval gate.
"""
import pytest
from ceo.db import create_task, get_task
from ceo.economics import calculate_economic_outcome, EconomicOutcome
from ceo.safety import SafetyPolicy, evaluate_safety
from ceo.orchestration import (
    assign_task,
    approve_task,
    claim_task,
    complete_task,
    ApprovalRequiredError,
)


PERMISSIVE = SafetyPolicy(require_approval_for_side_effects=False, max_automated_spend=1000.0)
STRICT = SafetyPolicy(require_approval_for_side_effects=True, max_automated_spend=0.0)
MEDIUM = SafetyPolicy(require_approval_for_side_effects=False, max_automated_spend=10.0)


class TestEconomicPlanStorage:
    def test_economic_plan_stored_in_input_json(self, db):
        plan = {"spend": 20.0, "currency": "USD", "revenue_estimate": 100.0}
        task_id = create_task(db, "With plan", input_data={"economic_plan": plan})
        task = get_task(db, task_id)
        assert task["input_json"]["economic_plan"]["spend"] == 20.0

    def test_task_without_economic_plan_ok(self, db):
        task_id = create_task(db, "No plan", input_data={"key": "value"})
        task = get_task(db, task_id)
        assert task["input_json"].get("economic_plan") is None

    def test_multiple_economic_plan_fields_stored(self, db):
        plan = {
            "spend": 15.0,
            "fees": 2.0,
            "revenue_estimate": 80.0,
            "max_automated_spend": 5.0,
            "currency": "USD",
        }
        task_id = create_task(db, "Full plan", input_data={"economic_plan": plan})
        task = get_task(db, task_id)
        stored_plan = task["input_json"]["economic_plan"]
        assert stored_plan["fees"] == 2.0
        assert stored_plan["revenue_estimate"] == 80.0


class TestEconomicPlanSafetyEvaluation:
    def test_plan_exceeding_limit_requires_approval(self):
        policy = SafetyPolicy(max_automated_spend=5.0)
        plan = {"spend": 20.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is True
        assert decision.action_type == "economic_spend"

    def test_plan_within_limit_allowed(self):
        policy = SafetyPolicy(max_automated_spend=50.0)
        plan = {"spend": 20.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is False

    def test_missing_spend_defaults_to_zero(self):
        policy = SafetyPolicy(max_automated_spend=5.0)
        plan = {"revenue_estimate": 100.0}
        decision = evaluate_safety(policy, side_effect_type=None, economic_plan=plan)
        assert decision.requires_approval is False


class TestEconomicTaskLifecycle:
    def test_low_spend_task_runs_without_approval(self, db):
        task_id = create_task(
            db, "Small spend", input_data={"economic_plan": {"spend": 5.0}}
        )
        result = assign_task(db, task_id, policy=MEDIUM)
        assert result["status"] == "assigned"

        result = claim_task(db, task_id, agent_id="worker-1")
        assert result["status"] == "in_progress"

    def test_high_spend_task_blocked_requires_approval(self, db):
        task_id = create_task(
            db, "Big spend", input_data={"economic_plan": {"spend": 100.0}}
        )
        result = assign_task(db, task_id, policy=MEDIUM)
        assert result["status"] == "blocked_approval"
        assert get_task(db, task_id)["status"] == "blocked_approval"

    def test_approved_economic_task_becomes_claimable(self, db):
        task_id = create_task(
            db, "Approved spend", input_data={"economic_plan": {"spend": 100.0}}
        )
        assign_result = assign_task(db, task_id, policy=MEDIUM)
        assert assign_result["status"] == "blocked_approval"

        approve_result = approve_task(db, assign_result["approval_id"], approved=True)
        assert approve_result["task_status"] == "assigned"

        claim_result = claim_task(db, task_id, agent_id="worker-1")
        assert claim_result["status"] == "in_progress"

    def test_economic_approval_bypass_prevented(self, db):
        """The bug fix: pending economic_spend approval blocks claim_task."""
        task_id = create_task(
            db, "Bypass attempt", input_data={"economic_plan": {"spend": 50.0}}
        )
        assign_result = assign_task(db, task_id, policy=MEDIUM)
        assert assign_result["status"] == "blocked_approval"

        # Force task to 'assigned' without clearing the pending approval
        db.execute("UPDATE ceo_tasks SET status='assigned' WHERE task_id=?", (task_id,))

        # Must still fail at the claim gate
        with pytest.raises(ApprovalRequiredError):
            claim_task(db, task_id, agent_id="attacker")

    def test_full_economic_lifecycle(self, db):
        task_id = create_task(
            db,
            "Full lifecycle",
            workstream_id="research",
            input_data={"economic_plan": {"spend": 20.0, "revenue_estimate": 80.0}},
        )
        assign_result = assign_task(db, task_id, policy=MEDIUM)
        assert assign_result["status"] == "blocked_approval"

        approve_task(db, assign_result["approval_id"], approved=True, decided_by="human_ceo")

        claim_task(db, task_id, agent_id="research-worker")
        result_id = complete_task(db, task_id, output={"revenue": 80.0, "spend": 20.0})

        task = get_task(db, task_id)
        assert task["status"] == "completed"
        assert result_id is not None


class TestEconomicOutcomeSerialization:
    def test_outcome_from_completed_task_result(self, db):
        task_id = create_task(db, "Outcome task", input_data={"economic_plan": {"spend": 10.0}})
        assign_task(db, task_id, policy=PERMISSIVE)
        claim_task(db, task_id, agent_id="w")
        complete_task(db, task_id, output={"revenue": 50.0, "spend": 10.0})

        outcome = calculate_economic_outcome(revenue=50.0, spend=10.0)
        assert outcome.profit == 40.0
        assert outcome.roas == pytest.approx(5.0)

    def test_serialized_outcome_round_trips(self):
        o = calculate_economic_outcome(revenue=80, spend=20, fees=5)
        d = o.to_dict()
        o2 = EconomicOutcome.from_dict(d)
        assert o2.profit == o.profit
        assert o2.roi == pytest.approx(o.roi)


class TestTasksWithoutEconomicPlanUnchanged:
    def test_plain_task_assigns_and_claims(self, db):
        task_id = create_task(db, "Plain task")
        assign_task(db, task_id, policy=PERMISSIVE)
        claim_task(db, task_id, agent_id="w")
        assert get_task(db, task_id)["status"] == "in_progress"

    def test_plain_task_no_approval_created(self, db):
        task_id = create_task(db, "No approval task")
        result = assign_task(db, task_id, policy=PERMISSIVE)
        assert result["approval_id"] is None

    def test_input_data_preserved_without_economic_plan(self, db):
        task_id = create_task(db, "Data task", input_data={"foo": "bar", "count": 42})
        task = get_task(db, task_id)
        assert task["input_json"]["foo"] == "bar"
        assert task["input_json"]["count"] == 42


class TestEconomicPlansWithinPolicy:
    def test_plan_within_policy_no_approval(self, db):
        task_id = create_task(
            db, "Within policy", input_data={"economic_plan": {"spend": 8.0}}
        )
        result = assign_task(db, task_id, policy=MEDIUM)
        assert result["status"] == "assigned"
        assert result["approval_id"] is None

    def test_exact_limit_no_approval(self, db):
        task_id = create_task(
            db, "At limit", input_data={"economic_plan": {"spend": 10.0}}
        )
        result = assign_task(db, task_id, policy=MEDIUM)
        assert result["status"] == "assigned"


class TestNegativePlannedSpendRejected:
    def test_negative_planned_spend_rejected_at_assign(self, db):
        task_id = create_task(
            db, "Bad plan", input_data={"economic_plan": {"spend": -5.0}}
        )
        with pytest.raises(ValueError):
            assign_task(db, task_id, policy=PERMISSIVE)

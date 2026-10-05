import pytest
from ceo.db import create_task, get_task, create_approval, decide_approval, init_db
from ceo.orchestration import (
    assign_task,
    approve_task,
    claim_task,
    complete_task,
    fail_task,
    transition_task,
    create_and_queue_task,
    ApprovalRequiredError,
    TaskNotFoundError,
    InvalidTransitionError,
)
from ceo.safety import SafetyPolicy, SIDE_EFFECT_LISTING, SIDE_EFFECT_NONE


PERMISSIVE_POLICY = SafetyPolicy(
    require_approval_for_side_effects=False,
    max_automated_spend=1000.0,
)

STRICT_POLICY = SafetyPolicy(
    require_approval_for_side_effects=True,
    max_automated_spend=0.0,
)


class TestAssignTask:
    def test_assign_simple_task(self, db):
        task_id = create_task(db, "Simple task")
        result = assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        assert result["status"] == "assigned"
        assert get_task(db, task_id)["status"] == "assigned"

    def test_assign_nonexistent_task(self, db):
        with pytest.raises(TaskNotFoundError):
            assign_task(db, "bad-id", policy=PERMISSIVE_POLICY)

    def test_assign_non_queued_task(self, db):
        task_id = create_task(db, "Task")
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        with pytest.raises(InvalidTransitionError):
            assign_task(db, task_id, policy=PERMISSIVE_POLICY)

    def test_assign_with_side_effect_blocks(self, db):
        task_id = create_task(db, "Listing", side_effect_type=SIDE_EFFECT_LISTING)
        result = assign_task(db, task_id, policy=STRICT_POLICY)
        assert result["status"] == "blocked_approval"
        assert result["approval_id"] is not None
        assert get_task(db, task_id)["status"] == "blocked_approval"

    def test_assign_with_economic_plan_exceeding_limit_blocks(self, db):
        task_id = create_task(db, "Big spend", input_data={"economic_plan": {"spend": 100.0}})
        result = assign_task(db, task_id, policy=SafetyPolicy(max_automated_spend=5.0))
        assert result["status"] == "blocked_approval"

    def test_assign_within_spend_limit_ok(self, db):
        task_id = create_task(db, "Small spend", input_data={"economic_plan": {"spend": 3.0}})
        result = assign_task(db, task_id, policy=SafetyPolicy(max_automated_spend=10.0))
        assert result["status"] == "assigned"


class TestApproveTask:
    def _blocked_task(self, db):
        task_id = create_task(db, "Needs approval", side_effect_type=SIDE_EFFECT_LISTING)
        result = assign_task(db, task_id, policy=STRICT_POLICY)
        return task_id, result["approval_id"]

    def test_approve_moves_to_assigned(self, db):
        task_id, approval_id = self._blocked_task(db)
        result = approve_task(db, approval_id, approved=True)
        assert result["task_status"] == "assigned"
        assert get_task(db, task_id)["status"] == "assigned"

    def test_reject_cancels_task(self, db):
        task_id, approval_id = self._blocked_task(db)
        result = approve_task(db, approval_id, approved=False)
        assert result["task_status"] == "cancelled"
        assert get_task(db, task_id)["status"] == "cancelled"

    def test_approve_nonexistent_raises(self, db):
        with pytest.raises(Exception):
            approve_task(db, "bad-approval-id", approved=True)


class TestClaimTask:
    def test_claim_assigned_task(self, db):
        task_id = create_task(db, "Claimable")
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        result = claim_task(db, task_id, agent_id="agent-1")
        assert result["status"] == "in_progress"
        assert get_task(db, task_id)["status"] == "in_progress"

    def test_claim_non_assigned_raises(self, db):
        task_id = create_task(db, "Queued only")
        with pytest.raises(InvalidTransitionError):
            claim_task(db, task_id, agent_id="agent-1")

    def test_claim_blocked_task_raises(self, db):
        task_id = create_task(db, "Blocked", side_effect_type=SIDE_EFFECT_LISTING)
        assign_task(db, task_id, policy=STRICT_POLICY)
        with pytest.raises((InvalidTransitionError, ApprovalRequiredError)):
            claim_task(db, task_id, agent_id="agent-1")

    def test_claim_nonexistent_raises(self, db):
        with pytest.raises(TaskNotFoundError):
            claim_task(db, "bad-id", agent_id="agent-1")

    def test_claim_sets_agent_id(self, db):
        task_id = create_task(db, "With agent")
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        claim_task(db, task_id, agent_id="special-agent")
        task = get_task(db, task_id)
        assert task["agent_id"] == "special-agent"


class TestClaimWithPendingApproval:
    """
    Critical: verify the economic approval bypass bug is fixed.
    A task with economic_spend approval pending must not be claimable.
    """

    def test_economic_approval_pending_blocks_claim(self, db):
        task_id = create_task(
            db,
            "Big spend task",
            input_data={"economic_plan": {"spend": 50.0}},
        )
        result = assign_task(db, task_id, policy=SafetyPolicy(max_automated_spend=5.0))
        assert result["status"] == "blocked_approval"

        # Manually force status to 'assigned' to simulate incomplete approval flow
        db.execute("UPDATE ceo_tasks SET status='assigned' WHERE task_id=?", (task_id,))

        # claim_task MUST still block because the approval is still pending
        with pytest.raises(ApprovalRequiredError):
            claim_task(db, task_id, agent_id="agent-1")

    def test_after_approval_claim_succeeds(self, db):
        task_id = create_task(
            db,
            "Big spend approved",
            input_data={"economic_plan": {"spend": 50.0}},
        )
        result = assign_task(db, task_id, policy=SafetyPolicy(max_automated_spend=5.0))
        approval_id = result["approval_id"]

        approve_task(db, approval_id, approved=True)
        # Now should be assigned with no pending approvals
        assert get_task(db, task_id)["status"] == "assigned"

        result = claim_task(db, task_id, agent_id="agent-1")
        assert result["status"] == "in_progress"

    def test_rejected_task_not_claimable(self, db):
        task_id = create_task(
            db,
            "Rejected spend",
            input_data={"economic_plan": {"spend": 50.0}},
        )
        result = assign_task(db, task_id, policy=SafetyPolicy(max_automated_spend=5.0))
        approve_task(db, result["approval_id"], approved=False)
        assert get_task(db, task_id)["status"] == "cancelled"

    def test_side_effect_null_economic_approval_still_blocked(self, db):
        """Economic-only approval (side_effect_type=NULL) cannot be bypassed."""
        task_id = create_task(
            db,
            "Economic only, no side effect",
            side_effect_type=None,
            input_data={"economic_plan": {"spend": 100.0}},
        )
        assign_result = assign_task(db, task_id, policy=SafetyPolicy(max_automated_spend=5.0))
        assert assign_result["status"] == "blocked_approval"
        # Force assign status without clearing approval
        db.execute("UPDATE ceo_tasks SET status='assigned' WHERE task_id=?", (task_id,))
        with pytest.raises(ApprovalRequiredError):
            claim_task(db, task_id, agent_id="agent-1")


class TestCompleteTask:
    def _running_task(self, db):
        task_id = create_task(db, "Running")
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        claim_task(db, task_id, agent_id="agent-1")
        return task_id

    def test_complete_task(self, db):
        task_id = self._running_task(db)
        result_id = complete_task(db, task_id, output={"result": "done"})
        assert result_id is not None
        assert get_task(db, task_id)["status"] == "completed"

    def test_complete_non_running_raises(self, db):
        task_id = create_task(db, "Queued")
        with pytest.raises(InvalidTransitionError):
            complete_task(db, task_id)

    def test_complete_nonexistent_raises(self, db):
        with pytest.raises(TaskNotFoundError):
            complete_task(db, "bad-id")


class TestFailTask:
    def _running_task(self, db):
        task_id = create_task(db, "Running", max_retries=3)
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        claim_task(db, task_id, agent_id="agent-1")
        return task_id

    def test_fail_without_retry(self, db):
        task_id = self._running_task(db)
        result = fail_task(db, task_id, error="something broke", retry=False)
        assert result["status"] == "failed"
        assert get_task(db, task_id)["status"] == "failed"

    def test_fail_with_retry_requeues(self, db):
        task_id = self._running_task(db)
        result = fail_task(db, task_id, error="transient error", retry=True)
        assert result["status"] == "queued"
        assert result["retry_count"] == 1

    def test_fail_exceeds_max_retries(self, db):
        task_id = create_task(db, "Max retries", max_retries=0)
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        claim_task(db, task_id, agent_id="agent-1")
        result = fail_task(db, task_id, error="permanent error", retry=True)
        assert result["status"] == "failed"


class TestTransitionTask:
    def test_valid_transition(self, db):
        task_id = create_task(db, "T")
        transition_task(db, task_id, "assigned")
        assert get_task(db, task_id)["status"] == "assigned"

    def test_invalid_transition_raises(self, db):
        task_id = create_task(db, "T")
        with pytest.raises(InvalidTransitionError):
            transition_task(db, task_id, "completed")

    def test_completed_task_no_transition(self, db):
        task_id = create_task(db, "T")
        assign_task(db, task_id, policy=PERMISSIVE_POLICY)
        claim_task(db, task_id, agent_id="a")
        complete_task(db, task_id)
        with pytest.raises(InvalidTransitionError):
            transition_task(db, task_id, "assigned")


class TestCreateAndQueueTask:
    def test_creates_queued_task(self, db):
        task_id = create_and_queue_task(db, title="New task")
        task = get_task(db, task_id)
        assert task["status"] == "queued"
        assert task["title"] == "New task"

    def test_creates_with_workstream(self, db):
        task_id = create_and_queue_task(db, title="WS task", workstream_id="research")
        task = get_task(db, task_id)
        assert task["workstream_id"] == "research"

    def test_creates_with_capabilities(self, db):
        task_id = create_and_queue_task(
            db, title="Cap task", required_capabilities=["research", "analysis"]
        )
        task = get_task(db, task_id)
        assert "research" in task["required_capabilities"]

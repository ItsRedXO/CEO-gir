import pytest
from ceo.db import create_task, update_task_status, get_task
from ceo.economics import calculate_economic_outcome
from ceo.learning import (
    EVAL_SCALED, EVAL_VALIDATED, EVAL_IMPROVED,
    EVAL_NEEDS_MORE_EVIDENCE, EVAL_EXECUTION_FAILED,
)
from ceo.replanning import (
    determine_next_action,
    replan_after_evaluation,
    get_next_queued_tasks,
    get_ceo_decision_context,
    REPLAN_SCALE, REPLAN_CONTINUE, REPLAN_IMPROVE,
    REPLAN_RESEARCH, REPLAN_PAUSE, REPLAN_KILL,
)


def eval_result(evaluation, roi=None, profit=0):
    return {"evaluation": evaluation, "roi": roi, "profit": profit, "reason": "test"}


class TestDetermineNextAction:
    def test_scaled_returns_scale(self):
        assert determine_next_action(eval_result(EVAL_SCALED, roi=3.0)) == REPLAN_SCALE

    def test_validated_returns_continue(self):
        assert determine_next_action(eval_result(EVAL_VALIDATED, roi=0.6)) == REPLAN_CONTINUE

    def test_improved_returns_improve(self):
        assert determine_next_action(eval_result(EVAL_IMPROVED, roi=0.1)) == REPLAN_IMPROVE

    def test_needs_evidence_returns_research(self):
        assert determine_next_action(eval_result(EVAL_NEEDS_MORE_EVIDENCE)) == REPLAN_RESEARCH

    def test_failed_with_bad_roi_returns_kill(self):
        assert determine_next_action(eval_result(EVAL_EXECUTION_FAILED, roi=-0.9)) == REPLAN_KILL

    def test_failed_without_roi_returns_pause(self):
        assert determine_next_action(eval_result(EVAL_EXECUTION_FAILED, roi=None)) == REPLAN_PAUSE

    def test_failed_with_minor_loss_returns_pause(self):
        assert determine_next_action(eval_result(EVAL_EXECUTION_FAILED, roi=-0.3)) == REPLAN_PAUSE


class TestReplanAfterEvaluation:
    def _make_task(self, db, workstream_id="research"):
        task_id = create_task(db, "Source task", workstream_id=workstream_id)
        update_task_status(db, task_id, "completed")
        return task_id

    def test_research_replan_creates_task(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_NEEDS_MORE_EVIDENCE))
        assert new_id is not None
        new_task = get_task(db, new_id)
        assert new_task["status"] == "queued"
        assert "Research" in new_task["title"]

    def test_scale_replan_creates_scale_task(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_SCALED, roi=3.0))
        assert new_id is not None
        new_task = get_task(db, new_id)
        assert "Scale" in new_task["title"]

    def test_improve_replan_creates_improve_task(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_IMPROVED, roi=0.1))
        new_task = get_task(db, new_id)
        assert "Improve" in new_task["title"]

    def test_continue_replan_creates_continue_task(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_VALIDATED, roi=0.8))
        new_task = get_task(db, new_id)
        assert "Continue" in new_task["title"]

    def test_pause_returns_none(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_EXECUTION_FAILED, roi=None))
        assert new_id is None

    def test_kill_returns_none(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_EXECUTION_FAILED, roi=-0.8))
        assert new_id is None

    def test_nonexistent_task_returns_none(self, db):
        new_id = replan_after_evaluation(db, "bad-id", eval_result(EVAL_NEEDS_MORE_EVIDENCE))
        assert new_id is None

    def test_research_task_has_parent_task_id(self, db):
        task_id = self._make_task(db)
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_NEEDS_MORE_EVIDENCE))
        new_task = get_task(db, new_id)
        assert new_task["parent_task_id"] == task_id

    def test_research_task_inherits_workstream(self, db):
        task_id = create_task(db, "Etsy task", workstream_id="etsy")
        update_task_status(db, task_id, "completed")
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_NEEDS_MORE_EVIDENCE))
        new_task = get_task(db, new_id)
        assert new_task["workstream_id"] == "etsy"

    def test_opportunity_id_propagated(self, db):
        task_id = create_task(db, "Opp task", opportunity_id="opp-123", workstream_id="research")
        update_task_status(db, task_id, "completed")
        new_id = replan_after_evaluation(db, task_id, eval_result(EVAL_NEEDS_MORE_EVIDENCE), opportunity_id="opp-123")
        new_task = get_task(db, new_id)
        assert new_task["opportunity_id"] == "opp-123"


class TestGetNextQueuedTasks:
    def test_returns_queued_tasks(self, db):
        create_task(db, "Q1")
        create_task(db, "Q2")
        tasks = get_next_queued_tasks(db, limit=5)
        assert len(tasks) >= 2
        assert all(t["status"] == "queued" for t in tasks)

    def test_respects_limit(self, db):
        for i in range(10):
            create_task(db, f"Task {i}")
        tasks = get_next_queued_tasks(db, limit=3)
        assert len(tasks) == 3


class TestGetCEODecisionContext:
    def test_context_has_expected_keys(self, db):
        ctx = get_ceo_decision_context(db)
        assert "queued_count" in ctx
        assert "in_progress_count" in ctx
        assert "blocked_count" in ctx
        assert "top_queued_tasks" in ctx
        assert "memory_count" in ctx
        assert "recent_lessons" in ctx

    def test_context_counts_queued_tasks(self, db):
        create_task(db, "Q1")
        create_task(db, "Q2")
        ctx = get_ceo_decision_context(db)
        assert ctx["queued_count"] >= 2

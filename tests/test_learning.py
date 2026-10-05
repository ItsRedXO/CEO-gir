import pytest
from ceo.db import create_task, update_task_status, get_memories
from ceo.economics import calculate_economic_outcome
from ceo.learning import (
    evaluate_task_outcome,
    learn_from_completion,
    persist_lesson,
    get_workstream_lessons,
    EVAL_EXECUTION_FAILED,
    EVAL_NEEDS_MORE_EVIDENCE,
    EVAL_VALIDATED,
    EVAL_SCALED,
    EVAL_IMPROVED,
    EVAL_EVALUATE_NEXT_STEP,
)


def make_completed_task(db, title="Task", workstream_id="research"):
    task_id = create_task(db, title, workstream_id=workstream_id)
    update_task_status(db, task_id, "completed")
    return task_id


def make_failed_task(db, title="Failed Task"):
    task_id = create_task(db, title)
    update_task_status(db, task_id, "failed")
    return task_id


class TestEvaluateTaskOutcome:
    def test_failed_task_is_execution_failed(self, db):
        task_id = make_failed_task(db)
        result = evaluate_task_outcome(db, task_id)
        assert result["evaluation"] == EVAL_EXECUTION_FAILED

    def test_task_not_found(self, db):
        result = evaluate_task_outcome(db, "nonexistent")
        assert result["evaluation"] == EVAL_EXECUTION_FAILED

    def test_completed_no_outcome_needs_evidence(self, db):
        task_id = make_completed_task(db)
        result = evaluate_task_outcome(db, task_id, economic_outcome=None)
        assert result["evaluation"] == EVAL_NEEDS_MORE_EVIDENCE

    def test_high_roi_is_scaled(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=100, spend=20)
        # profit=80, cost=20, roi=4.0 → scaled
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] == EVAL_SCALED

    def test_medium_roi_is_validated(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=80, spend=50)
        # profit=30, cost=50, roi=0.6 → validated
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] == EVAL_VALIDATED

    def test_low_positive_roi_is_improved(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=55, spend=50)
        # profit=5, cost=50, roi=0.1 → improved
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] == EVAL_IMPROVED

    def test_negative_roi_needs_evidence(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=10, spend=50)
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] == EVAL_NEEDS_MORE_EVIDENCE

    def test_negative_profit_is_failed(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=5, spend=50)
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] in (EVAL_EXECUTION_FAILED, EVAL_NEEDS_MORE_EVIDENCE)

    def test_zero_cost_with_revenue_is_validated(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=50, spend=0, fees=0)
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] == EVAL_VALIDATED

    def test_zero_cost_no_revenue_needs_evidence(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=0, spend=0, fees=0)
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["evaluation"] == EVAL_NEEDS_MORE_EVIDENCE

    def test_in_progress_task_returns_evaluate_next(self, db):
        task_id = create_task(db, "Running")
        update_task_status(db, task_id, "in_progress")
        result = evaluate_task_outcome(db, task_id)
        assert result["evaluation"] == EVAL_EVALUATE_NEXT_STEP

    def test_evaluation_includes_task_id(self, db):
        task_id = make_completed_task(db)
        outcome = calculate_economic_outcome(revenue=100, spend=20)
        result = evaluate_task_outcome(db, task_id, economic_outcome=outcome)
        assert result["task_id"] == task_id


class TestPersistLesson:
    def test_lesson_saved_to_memory(self, db):
        memory_id = persist_lesson(db, "workstream:research", "Research works", confidence=0.8)
        assert memory_id is not None
        memories = get_memories(db, category="workstream:research")
        assert any(m["content"] == "Research works" for m in memories)

    def test_multiple_lessons_stored(self, db):
        persist_lesson(db, "workstream:etsy", "Etsy lesson 1")
        persist_lesson(db, "workstream:etsy", "Etsy lesson 2")
        lessons = get_workstream_lessons(db, "etsy")
        assert len(lessons) == 2


class TestLearnFromCompletion:
    def test_scaled_task_saves_lesson(self, db):
        task_id = create_task(db, "Scale me", workstream_id="research")
        update_task_status(db, task_id, "completed")
        outcome = calculate_economic_outcome(revenue=200, spend=40)
        result = learn_from_completion(db, task_id, outcome)
        assert result["evaluation"] == EVAL_SCALED
        lessons = get_workstream_lessons(db, "research")
        assert len(lessons) > 0

    def test_failed_task_saves_lesson(self, db):
        task_id = make_failed_task(db)
        # Adjust workstream
        db.execute("UPDATE ceo_tasks SET workstream_id='content' WHERE task_id=?", (task_id,))
        result = learn_from_completion(db, task_id)
        assert result["evaluation"] == EVAL_EXECUTION_FAILED
        lessons = get_workstream_lessons(db, "content")
        assert len(lessons) > 0

    def test_no_outcome_task_saves_evidence_lesson(self, db):
        task_id = make_completed_task(db, workstream_id="affiliate")
        result = learn_from_completion(db, task_id, economic_outcome=None)
        assert result["evaluation"] == EVAL_NEEDS_MORE_EVIDENCE
        lessons = get_workstream_lessons(db, "affiliate")
        assert len(lessons) > 0

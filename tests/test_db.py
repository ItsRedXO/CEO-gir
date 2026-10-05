import pytest
from ceo.db import (
    create_task, get_task, update_task_status, list_tasks,
    create_approval, get_pending_approvals, decide_approval,
    has_approved_record, has_any_pending_approval,
    record_task_result, record_metric, record_opportunity_outcome,
    set_state, get_state, add_memory, get_memories, get_daily_revenue,
    get_total_metrics, CEO_SCHEMA_VERSION,
)


class TestSchemaVersion:
    def test_schema_version_is_four(self):
        assert CEO_SCHEMA_VERSION == 4


class TestCreateTask:
    def test_creates_task_with_queued_status(self, db):
        task_id = create_task(db, "Test Task")
        task = get_task(db, task_id)
        assert task is not None
        assert task["status"] == "queued"

    def test_creates_task_with_title(self, db):
        task_id = create_task(db, "My Title")
        assert get_task(db, task_id)["title"] == "My Title"

    def test_creates_task_with_description(self, db):
        task_id = create_task(db, "T", description="Desc")
        assert get_task(db, task_id)["description"] == "Desc"

    def test_creates_task_with_workstream(self, db):
        task_id = create_task(db, "T", workstream_id="research")
        assert get_task(db, task_id)["workstream_id"] == "research"

    def test_creates_task_with_priority(self, db):
        task_id = create_task(db, "T", priority=2)
        assert get_task(db, task_id)["priority"] == 2

    def test_creates_task_with_side_effect_type(self, db):
        task_id = create_task(db, "T", side_effect_type="listing")
        assert get_task(db, task_id)["side_effect_type"] == "listing"

    def test_creates_task_with_input_data(self, db):
        task_id = create_task(db, "T", input_data={"key": "val"})
        task = get_task(db, task_id)
        assert task["input_json"]["key"] == "val"

    def test_creates_task_with_parent(self, db):
        parent_id = create_task(db, "Parent")
        child_id = create_task(db, "Child", parent_task_id=parent_id)
        assert get_task(db, child_id)["parent_task_id"] == parent_id

    def test_creates_task_with_capabilities(self, db):
        task_id = create_task(db, "T", required_capabilities=["research"])
        task = get_task(db, task_id)
        assert "research" in task["required_capabilities"]

    def test_returns_unique_ids(self, db):
        ids = {create_task(db, f"Task {i}") for i in range(10)}
        assert len(ids) == 10


class TestGetTask:
    def test_returns_none_for_missing(self, db):
        assert get_task(db, "nonexistent") is None

    def test_returns_task_by_id(self, db):
        task_id = create_task(db, "X")
        assert get_task(db, task_id)["task_id"] == task_id


class TestUpdateTaskStatus:
    def test_updates_status(self, db):
        task_id = create_task(db, "T")
        update_task_status(db, task_id, "assigned")
        assert get_task(db, task_id)["status"] == "assigned"

    def test_updates_result_json(self, db):
        task_id = create_task(db, "T")
        update_task_status(db, task_id, "completed", result_json={"out": 1})
        task = get_task(db, task_id)
        assert task["result_json"]["out"] == 1


class TestListTasks:
    def test_lists_all_tasks(self, db):
        create_task(db, "A")
        create_task(db, "B")
        tasks = list_tasks(db)
        assert len(tasks) >= 2

    def test_filters_by_status(self, db):
        task_id = create_task(db, "Q")
        update_task_status(db, task_id, "assigned")
        tasks = list_tasks(db, status="assigned")
        assert all(t["status"] == "assigned" for t in tasks)

    def test_filters_by_workstream(self, db):
        create_task(db, "R", workstream_id="research")
        create_task(db, "C", workstream_id="content")
        tasks = list_tasks(db, workstream_id="research")
        assert all(t["workstream_id"] == "research" for t in tasks)

    def test_respects_limit(self, db):
        for i in range(10):
            create_task(db, f"Task {i}")
        tasks = list_tasks(db, limit=3)
        assert len(tasks) == 3


class TestApprovals:
    def test_create_approval(self, db):
        task_id = create_task(db, "T")
        approval_id = create_approval(db, task_id, "side_effect")
        assert approval_id is not None

    def test_get_pending_approvals(self, db):
        task_id = create_task(db, "T")
        create_approval(db, task_id, "side_effect")
        pending = get_pending_approvals(db, task_id)
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

    def test_decide_approval_approved(self, db):
        task_id = create_task(db, "T")
        approval_id = create_approval(db, task_id, "side_effect")
        decide_approval(db, approval_id, approved=True)
        assert has_approved_record(db, task_id)

    def test_decide_approval_rejected(self, db):
        task_id = create_task(db, "T")
        approval_id = create_approval(db, task_id, "side_effect")
        decide_approval(db, approval_id, approved=False)
        assert not has_approved_record(db, task_id)

    def test_has_any_pending_true(self, db):
        task_id = create_task(db, "T")
        create_approval(db, task_id, "economic_spend")
        assert has_any_pending_approval(db, task_id) is True

    def test_has_any_pending_false_after_decision(self, db):
        task_id = create_task(db, "T")
        approval_id = create_approval(db, task_id, "economic_spend")
        decide_approval(db, approval_id, approved=True)
        assert has_any_pending_approval(db, task_id) is False

    def test_has_approved_record_by_action_type(self, db):
        task_id = create_task(db, "T")
        approval_id = create_approval(db, task_id, "economic_spend")
        decide_approval(db, approval_id, approved=True)
        assert has_approved_record(db, task_id, action_type="economic_spend")
        assert not has_approved_record(db, task_id, action_type="side_effect")


class TestTaskResults:
    def test_record_task_result(self, db):
        task_id = create_task(db, "T")
        result_id = record_task_result(db, task_id, "success", output={"x": 1})
        assert result_id is not None

    def test_result_stored_with_error(self, db):
        task_id = create_task(db, "T")
        result_id = record_task_result(db, task_id, "failure", error="oops")
        assert result_id is not None


class TestMetrics:
    def test_record_metric(self, db):
        obs_id = record_metric(db, "revenue", 50.0, workstream_id="research")
        assert obs_id is not None

    def test_get_total_metrics(self, db):
        metrics = get_total_metrics(db)
        assert "total_revenue" in metrics
        assert "task_counts" in metrics


class TestOpportunityOutcomes:
    def test_record_outcome(self, db):
        outcome_id = record_opportunity_outcome(
            db, "opp-1", revenue=80, spend=20, fees=5, profit=55
        )
        assert outcome_id is not None

    def test_daily_revenue(self, db):
        record_opportunity_outcome(db, "opp-2", revenue=50, spend=10, fees=2, profit=38)
        rev = get_daily_revenue(db)
        assert rev >= 50


class TestStateAndMemory:
    def test_set_and_get_state(self, db):
        set_state(db, "test_key", {"value": 42})
        val = get_state(db, "test_key")
        assert val["value"] == 42

    def test_get_missing_state_default(self, db):
        assert get_state(db, "missing", default="x") == "x"

    def test_add_memory(self, db):
        memory_id = add_memory(db, "lesson", "Test lesson")
        assert memory_id is not None
        memories = get_memories(db, category="lesson")
        assert any(m["content"] == "Test lesson" for m in memories)

    def test_get_all_memories(self, db):
        add_memory(db, "cat1", "m1")
        add_memory(db, "cat2", "m2")
        memories = get_memories(db)
        assert len(memories) >= 2

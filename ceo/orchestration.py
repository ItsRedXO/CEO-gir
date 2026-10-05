"""
CEO GIR Orchestration layer.

Task lifecycle:
  queued → assigned → in_progress → completed / failed
  queued → assigned → blocked_approval → assigned → in_progress → ...

The key invariant fixed here: claim_task() checks ALL pending approvals
for a task, not just ones matching side_effect_type. This prevents
economic-only approvals (action_type='economic_spend', side_effect_type=NULL)
from being bypassed at the execution boundary.
"""
from __future__ import annotations

import sqlite3
import json
from typing import Optional

from .db import (
    create_task,
    get_task,
    update_task_status,
    create_approval,
    get_pending_approvals,
    decide_approval as db_decide_approval,
    has_approved_record,
    has_any_pending_approval,
    record_task_result,
)
from .economics import extract_economic_plan, validate_economic_plan
from .safety import SafetyPolicy, evaluate_safety, DEFAULT_POLICY


class OrchestrationError(Exception):
    pass


class ApprovalRequiredError(OrchestrationError):
    def __init__(self, task_id: str, action_type: str, reason: str):
        self.task_id = task_id
        self.action_type = action_type
        self.reason = reason
        super().__init__(f"Task {task_id} requires approval ({action_type}): {reason}")


class TaskNotFoundError(OrchestrationError):
    pass


class InvalidTransitionError(OrchestrationError):
    pass


VALID_TRANSITIONS = {
    "queued": {"assigned", "cancelled"},
    "assigned": {"in_progress", "blocked_approval", "cancelled", "queued"},
    "blocked_approval": {"assigned", "cancelled"},
    "in_progress": {"completed", "failed", "assigned"},
    "completed": set(),
    "failed": {"queued"},
    "cancelled": set(),
}


def transition_task(
    conn: sqlite3.Connection,
    task_id: str,
    new_status: str,
    result_json: dict = None,
) -> None:
    task = get_task(conn, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    current = task["status"]
    allowed = VALID_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition task {task_id} from '{current}' to '{new_status}'"
        )
    update_task_status(conn, task_id, new_status, result_json)


def assign_task(
    conn: sqlite3.Connection,
    task_id: str,
    policy: SafetyPolicy = None,
) -> dict:
    """
    Move a task from queued → assigned, or queued → blocked_approval if
    safety/economics requires human review.
    Returns {"status": "assigned"|"blocked_approval", "approval_id": ...}
    """
    if policy is None:
        policy = DEFAULT_POLICY

    task = get_task(conn, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    if task["status"] != "queued":
        raise InvalidTransitionError(
            f"Task {task_id} must be 'queued' to assign, got '{task['status']}'"
        )

    input_data = task.get("input_json") or {}
    if isinstance(input_data, str):
        try:
            input_data = json.loads(input_data)
        except json.JSONDecodeError:
            input_data = {}

    economic_plan = extract_economic_plan(input_data)
    if economic_plan:
        validate_economic_plan(economic_plan)

    decision = evaluate_safety(policy, task.get("side_effect_type"), economic_plan)

    if decision.requires_approval:
        update_task_status(conn, task_id, "blocked_approval")
        approval_id = create_approval(conn, task_id, decision.action_type, requested_by="ceo")
        return {"status": "blocked_approval", "approval_id": approval_id, "reason": decision.reason}

    update_task_status(conn, task_id, "assigned")
    return {"status": "assigned", "approval_id": None}


def approve_task(
    conn: sqlite3.Connection,
    approval_id: str,
    approved: bool,
    decided_by: str = "human",
    decision_note: str = "",
) -> dict:
    """
    Record a human approval decision and, if approved, move the task back to assigned.
    Returns {"task_id": ..., "task_status": ...}
    """
    row = conn.execute(
        "SELECT * FROM ceo_approvals WHERE approval_id=?", (approval_id,)
    ).fetchone()
    if row is None:
        raise OrchestrationError(f"Approval {approval_id} not found")

    task_id = row["task_id"]
    db_decide_approval(conn, approval_id, approved, decided_by, decision_note)

    if approved:
        # Only move to assigned if there are no remaining pending approvals
        if not has_any_pending_approval(conn, task_id):
            task = get_task(conn, task_id)
            if task and task["status"] == "blocked_approval":
                update_task_status(conn, task_id, "assigned")
        return {"task_id": task_id, "task_status": "assigned"}
    else:
        update_task_status(conn, task_id, "cancelled")
        return {"task_id": task_id, "task_status": "cancelled"}


def claim_task(
    conn: sqlite3.Connection,
    task_id: str,
    agent_id: str,
) -> dict:
    """
    Move a task from assigned → in_progress.

    BUG FIX: Previously only checked side_effect_type-based approvals.
    Now checks ALL pending approvals for the task, regardless of action_type.
    This prevents economic-only approvals (action_type='economic_spend',
    side_effect_type=NULL) from being bypassed at the execution gate.
    """
    task = get_task(conn, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    if task["status"] != "assigned":
        raise InvalidTransitionError(
            f"Task {task_id} must be 'assigned' to claim, got '{task['status']}'"
        )

    # Gate: block execution if ANY approval is still pending for this task
    if has_any_pending_approval(conn, task_id):
        raise ApprovalRequiredError(
            task_id=task_id,
            action_type="unknown",
            reason="task has pending approvals that must be resolved before execution",
        )

    # Gate: if task has a side_effect_type, require an approved record for it
    side_effect_type = task.get("side_effect_type")
    if side_effect_type and side_effect_type != "none":
        if not has_approved_record(conn, task_id, action_type="side_effect"):
            # Check for any approved record as fallback (legacy side_effect approval)
            if not has_approved_record(conn, task_id):
                raise ApprovalRequiredError(
                    task_id=task_id,
                    action_type="side_effect",
                    reason=f"side_effect_type '{side_effect_type}' requires an approved record",
                )

    conn.execute(
        "UPDATE ceo_tasks SET agent_id=?, updated_at=datetime('now') WHERE task_id=?",
        (agent_id, task_id),
    )
    update_task_status(conn, task_id, "in_progress")
    return {"task_id": task_id, "status": "in_progress", "agent_id": agent_id}


def complete_task(
    conn: sqlite3.Connection,
    task_id: str,
    output: dict = None,
    duration_ms: int = None,
) -> str:
    task = get_task(conn, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task {task_id} not found")
    if task["status"] != "in_progress":
        raise InvalidTransitionError(
            f"Task {task_id} must be 'in_progress' to complete, got '{task['status']}'"
        )
    result_id = record_task_result(conn, task_id, "success", output, duration_ms=duration_ms)
    update_task_status(conn, task_id, "completed", result_json=output)
    return result_id


def fail_task(
    conn: sqlite3.Connection,
    task_id: str,
    error: str,
    duration_ms: int = None,
    retry: bool = False,
) -> dict:
    task = get_task(conn, task_id)
    if task is None:
        raise TaskNotFoundError(f"Task {task_id} not found")

    retry_count = task.get("retry_count", 0)
    max_retries = task.get("max_retries", 3)

    record_task_result(conn, task_id, "failure", error=error, duration_ms=duration_ms)

    if retry and retry_count < max_retries:
        conn.execute(
            "UPDATE ceo_tasks SET retry_count=retry_count+1, updated_at=datetime('now') WHERE task_id=?",
            (task_id,),
        )
        update_task_status(conn, task_id, "queued")
        return {"task_id": task_id, "status": "queued", "retry_count": retry_count + 1}
    else:
        update_task_status(conn, task_id, "failed")
        return {"task_id": task_id, "status": "failed", "retry_count": retry_count}


def create_and_queue_task(
    conn: sqlite3.Connection,
    title: str,
    description: str = "",
    workstream_id: str = None,
    opportunity_id: str = None,
    priority: int = 5,
    side_effect_type: str = None,
    input_data: dict = None,
    required_capabilities: list = None,
    parent_task_id: str = None,
    created_by: str = "ceo",
    max_retries: int = 3,
) -> str:
    return create_task(
        conn,
        title=title,
        description=description,
        workstream_id=workstream_id,
        opportunity_id=opportunity_id,
        priority=priority,
        side_effect_type=side_effect_type,
        input_data=input_data,
        required_capabilities=required_capabilities,
        parent_task_id=parent_task_id,
        created_by=created_by,
        max_retries=max_retries,
    )

from __future__ import annotations

import sqlite3
from typing import Optional

from .db import create_task, get_task, get_memories, list_tasks
from .learning import (
    EVAL_EXECUTION_FAILED,
    EVAL_NEEDS_MORE_EVIDENCE,
    EVAL_VALIDATED,
    EVAL_SCALED,
    EVAL_IMPROVED,
)


REPLAN_CONTINUE = "continue"
REPLAN_SCALE = "scale"
REPLAN_RESEARCH = "research"
REPLAN_IMPROVE = "improve"
REPLAN_PAUSE = "pause"
REPLAN_KILL = "kill"


def determine_next_action(eval_result: dict) -> str:
    evaluation = eval_result.get("evaluation")
    roi = eval_result.get("roi")

    if evaluation == EVAL_SCALED:
        return REPLAN_SCALE
    elif evaluation == EVAL_VALIDATED:
        return REPLAN_CONTINUE
    elif evaluation == EVAL_IMPROVED:
        return REPLAN_IMPROVE
    elif evaluation == EVAL_NEEDS_MORE_EVIDENCE:
        return REPLAN_RESEARCH
    elif evaluation == EVAL_EXECUTION_FAILED:
        if roi is not None and roi < -0.5:
            return REPLAN_KILL
        return REPLAN_PAUSE
    return REPLAN_RESEARCH


def replan_after_evaluation(
    conn: sqlite3.Connection,
    task_id: str,
    eval_result: dict,
    opportunity_id: str = None,
) -> Optional[str]:
    """
    Determine the next task to create based on evaluation results.
    Returns the new task_id, or None if no follow-up is needed.
    """
    task = get_task(conn, task_id)
    if task is None:
        return None

    action = determine_next_action(eval_result)
    workstream_id = task.get("workstream_id")
    title_base = task.get("title", "Task")

    if action == REPLAN_RESEARCH:
        new_task_id = create_task(
            conn,
            title=f"Research follow-up: {title_base}",
            description=(
                f"Gather more evidence for workstream '{workstream_id}'. "
                f"Previous evaluation: {eval_result.get('reason')}"
            ),
            workstream_id=workstream_id,
            opportunity_id=opportunity_id or task.get("opportunity_id"),
            priority=4,
            input_data={
                "follow_up_for": task_id,
                "evaluation": eval_result,
                "research_goal": "gather revenue and cost evidence",
            },
            required_capabilities=["research"],
            parent_task_id=task_id,
            created_by="ceo_replan",
        )
        return new_task_id

    elif action == REPLAN_IMPROVE:
        new_task_id = create_task(
            conn,
            title=f"Improve: {title_base}",
            description=(
                f"Optimize workstream '{workstream_id}' to improve ROI. "
                f"Current: {eval_result.get('reason')}"
            ),
            workstream_id=workstream_id,
            opportunity_id=opportunity_id or task.get("opportunity_id"),
            priority=3,
            input_data={
                "improve_for": task_id,
                "evaluation": eval_result,
                "target": "improve_roi",
            },
            required_capabilities=["optimization"],
            parent_task_id=task_id,
            created_by="ceo_replan",
        )
        return new_task_id

    elif action == REPLAN_SCALE:
        new_task_id = create_task(
            conn,
            title=f"Scale: {title_base}",
            description=(
                f"Scale up workstream '{workstream_id}'. "
                f"ROI is positive: {eval_result.get('reason')}"
            ),
            workstream_id=workstream_id,
            opportunity_id=opportunity_id or task.get("opportunity_id"),
            priority=2,
            input_data={
                "scale_from": task_id,
                "evaluation": eval_result,
                "scale_target": "2x_volume",
            },
            required_capabilities=["scaling"],
            parent_task_id=task_id,
            created_by="ceo_replan",
        )
        return new_task_id

    elif action in (REPLAN_PAUSE, REPLAN_KILL):
        # No new task — CEO decides to pause or kill this workstream direction
        return None

    elif action == REPLAN_CONTINUE:
        # Create a continuation task for the same opportunity
        new_task_id = create_task(
            conn,
            title=f"Continue: {title_base}",
            description=f"Continue validated workstream '{workstream_id}'.",
            workstream_id=workstream_id,
            opportunity_id=opportunity_id or task.get("opportunity_id"),
            priority=5,
            input_data={
                "continue_from": task_id,
                "evaluation": eval_result,
            },
            required_capabilities=task.get("required_capabilities") or [],
            parent_task_id=task_id,
            created_by="ceo_replan",
        )
        return new_task_id

    return None


def get_next_queued_tasks(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    return list_tasks(conn, status="queued", limit=limit)


def get_ceo_decision_context(conn: sqlite3.Connection) -> dict:
    queued = list_tasks(conn, status="queued", limit=20)
    in_progress = list_tasks(conn, status="in_progress", limit=20)
    blocked = list_tasks(conn, status="blocked_approval", limit=20)
    memories = get_memories(conn)

    return {
        "queued_count": len(queued),
        "in_progress_count": len(in_progress),
        "blocked_count": len(blocked),
        "top_queued_tasks": queued[:5],
        "memory_count": len(memories),
        "recent_lessons": memories[:3],
    }

from __future__ import annotations

import sqlite3
from typing import Optional

from .db import get_task, get_memories, add_memory, record_metric
from .economics import EconomicOutcome


EVAL_EXECUTION_FAILED = "execution_failed"
EVAL_NEEDS_MORE_EVIDENCE = "needs_more_evidence"
EVAL_VALIDATED = "validated"
EVAL_SCALED = "scaled"
EVAL_IMPROVED = "improved"
EVAL_EVALUATE_NEXT_STEP = "evaluate_next_step"


def evaluate_task_outcome(
    conn: sqlite3.Connection,
    task_id: str,
    economic_outcome: Optional[EconomicOutcome] = None,
) -> dict:
    task = get_task(conn, task_id)
    if task is None:
        return {"evaluation": EVAL_EXECUTION_FAILED, "reason": "task not found"}

    status = task.get("status")
    result = task.get("result_json") or {}

    if status == "failed":
        return {
            "evaluation": EVAL_EXECUTION_FAILED,
            "task_id": task_id,
            "reason": "task ended in failed state",
        }

    if status != "completed":
        return {
            "evaluation": EVAL_EVALUATE_NEXT_STEP,
            "task_id": task_id,
            "reason": f"task status is '{status}', not yet completed",
        }

    if economic_outcome is None:
        return {
            "evaluation": EVAL_NEEDS_MORE_EVIDENCE,
            "task_id": task_id,
            "reason": "no economic outcome recorded — need revenue data",
        }

    profit = economic_outcome.profit
    roi = economic_outcome.roi
    revenue = economic_outcome.revenue

    if roi is None:
        # Zero-cost task — judge on revenue alone
        if revenue > 0:
            evaluation = EVAL_VALIDATED
            reason = f"zero-cost task generated ${revenue:.2f} revenue"
        else:
            evaluation = EVAL_NEEDS_MORE_EVIDENCE
            reason = "zero-cost task with no revenue — gather more evidence"
    elif roi >= 2.0:
        evaluation = EVAL_SCALED
        reason = f"ROI {roi:.1%} — ready to scale"
    elif roi >= 0.5:
        evaluation = EVAL_VALIDATED
        reason = f"ROI {roi:.1%} — validated opportunity"
    elif roi >= 0.0:
        evaluation = EVAL_IMPROVED
        reason = f"ROI {roi:.1%} — profitable but underperforming, needs improvement"
    else:
        evaluation = EVAL_NEEDS_MORE_EVIDENCE
        reason = f"ROI {roi:.1%} — negative, gather more evidence before killing"

    eval_result = {
        "evaluation": evaluation,
        "task_id": task_id,
        "reason": reason,
        "profit": profit,
        "roi": roi,
        "revenue": revenue,
    }

    # Record the evaluation as a metric
    record_metric(
        conn,
        metric_name=f"task_evaluation_{evaluation}",
        metric_value=profit,
        task_id=task_id,
        workstream_id=task.get("workstream_id"),
        context=eval_result,
    )

    return eval_result


def persist_lesson(
    conn: sqlite3.Connection,
    category: str,
    content: str,
    confidence: float = 1.0,
    context: dict = None,
) -> str:
    return add_memory(conn, category, content, confidence, context)


def get_workstream_lessons(conn: sqlite3.Connection, workstream_id: str) -> list[dict]:
    return get_memories(conn, category=f"workstream:{workstream_id}")


def learn_from_completion(
    conn: sqlite3.Connection,
    task_id: str,
    economic_outcome: Optional[EconomicOutcome] = None,
) -> dict:
    eval_result = evaluate_task_outcome(conn, task_id, economic_outcome)
    task = get_task(conn, task_id)
    if task is None:
        return eval_result

    evaluation = eval_result["evaluation"]
    workstream_id = task.get("workstream_id") or "unknown"

    if evaluation == EVAL_SCALED:
        lesson = f"Workstream {workstream_id} task '{task['title']}' achieved scale-worthy ROI."
        persist_lesson(conn, f"workstream:{workstream_id}", lesson, confidence=0.9, context=eval_result)
    elif evaluation == EVAL_EXECUTION_FAILED:
        lesson = f"Workstream {workstream_id} task '{task['title']}' failed. Reason: {eval_result.get('reason')}"
        persist_lesson(conn, f"workstream:{workstream_id}", lesson, confidence=0.7, context=eval_result)
    elif evaluation == EVAL_NEEDS_MORE_EVIDENCE:
        lesson = f"Workstream {workstream_id} task '{task['title']}' needs more data before conclusion."
        persist_lesson(conn, f"workstream:{workstream_id}", lesson, confidence=0.5, context=eval_result)

    return eval_result

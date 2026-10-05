"""
CEO GIR Health Monitor — tracks system health, task throughput, and anomalies.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class HealthCheck:
    name: str
    status: str  # ok | warn | error
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class SystemHealth:
    overall: str  # ok | warn | error
    checks: list[HealthCheck]
    score: float  # 0.0–1.0
    checked_at: str


def check_db_connectivity(conn: sqlite3.Connection) -> HealthCheck:
    try:
        conn.execute("SELECT 1").fetchone()
        return HealthCheck("db_connectivity", "ok", "Database responding")
    except Exception as e:
        return HealthCheck("db_connectivity", "error", f"DB error: {e}")


def check_task_queue_depth(conn: sqlite3.Connection, warn_threshold: int = 20, error_threshold: int = 50) -> HealthCheck:
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM ceo_tasks WHERE status='queued'"
        ).fetchone()
        depth = row["cnt"] if row else 0
        if depth >= error_threshold:
            status = "error"
            msg = f"Queue depth {depth} exceeds error threshold {error_threshold}"
        elif depth >= warn_threshold:
            status = "warn"
            msg = f"Queue depth {depth} approaching limit {warn_threshold}"
        else:
            status = "ok"
            msg = f"Queue depth {depth} within normal range"
        return HealthCheck("task_queue_depth", status, msg, value=float(depth), threshold=float(warn_threshold))
    except Exception as e:
        return HealthCheck("task_queue_depth", "error", f"Error: {e}")


def check_failure_rate(conn: sqlite3.Connection, warn_threshold: float = 0.25, error_threshold: float = 0.5) -> HealthCheck:
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
            FROM ceo_tasks
            WHERE created_at >= datetime('now', '-1 hour')
            """
        ).fetchone()
        total = row["total"] if row else 0
        failed = row["failed"] if row else 0
        if total == 0:
            return HealthCheck("failure_rate", "ok", "No recent tasks", value=0.0)
        rate = failed / total
        if rate >= error_threshold:
            status = "error"
            msg = f"Failure rate {rate:.0%} — above {error_threshold:.0%}"
        elif rate >= warn_threshold:
            status = "warn"
            msg = f"Failure rate {rate:.0%} — above warn threshold {warn_threshold:.0%}"
        else:
            status = "ok"
            msg = f"Failure rate {rate:.0%} — within normal range"
        return HealthCheck("failure_rate", status, msg, value=rate, threshold=warn_threshold)
    except Exception as e:
        return HealthCheck("failure_rate", "error", f"Error: {e}")


def check_blocked_approvals(conn: sqlite3.Connection, warn_threshold: int = 5, error_threshold: int = 15) -> HealthCheck:
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM ceo_tasks WHERE status='blocked_approval'"
        ).fetchone()
        count = row["cnt"] if row else 0
        if count >= error_threshold:
            status = "error"
            msg = f"{count} tasks blocked awaiting approval"
        elif count >= warn_threshold:
            status = "warn"
            msg = f"{count} tasks blocked — consider reviewing approvals"
        else:
            status = "ok"
            msg = f"{count} approval-blocked tasks"
        return HealthCheck("blocked_approvals", status, msg, value=float(count), threshold=float(warn_threshold))
    except Exception as e:
        return HealthCheck("blocked_approvals", "error", f"Error: {e}")


def check_stale_in_progress(conn: sqlite3.Connection, stale_minutes: int = 30) -> HealthCheck:
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM ceo_tasks
            WHERE status='in_progress'
              AND updated_at <= datetime('now', ? || ' minutes')
            """,
            (f"-{stale_minutes}",),
        ).fetchone()
        count = row["cnt"] if row else 0
        if count > 0:
            status = "warn"
            msg = f"{count} task(s) stuck in_progress for >{stale_minutes}m"
        else:
            status = "ok"
            msg = "No stale in_progress tasks"
        return HealthCheck("stale_in_progress", status, msg, value=float(count))
    except Exception as e:
        return HealthCheck("stale_in_progress", "error", f"Error: {e}")


def run_health_check(conn: sqlite3.Connection) -> SystemHealth:
    checks = [
        check_db_connectivity(conn),
        check_task_queue_depth(conn),
        check_failure_rate(conn),
        check_blocked_approvals(conn),
        check_stale_in_progress(conn),
    ]

    status_weights = {"ok": 1.0, "warn": 0.5, "error": 0.0}
    score = sum(status_weights[c.status] for c in checks) / len(checks)

    error_count = sum(1 for c in checks if c.status == "error")
    warn_count = sum(1 for c in checks if c.status == "warn")

    if error_count > 0:
        overall = "error"
    elif warn_count > 1:
        overall = "warn"
    else:
        overall = "ok"

    return SystemHealth(
        overall=overall,
        checks=checks,
        score=round(score, 2),
        checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def health_to_dict(health: SystemHealth) -> dict:
    return {
        "overall": health.overall,
        "score": health.score,
        "checked_at": health.checked_at,
        "checks": [
            {
                "name": c.name,
                "status": c.status,
                "message": c.message,
                "value": c.value,
                "threshold": c.threshold,
            }
            for c in health.checks
        ],
    }

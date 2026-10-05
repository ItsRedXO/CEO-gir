"""
Auto-Pilot — runs complete execution cycles autonomously.

One cycle does:
  1. CEO Brain: decide and create new tasks
  2. Assign all queued tasks that don't need approval
  3. Dispatch all assigned tasks through the dispatcher
  4. Return a full cycle report

The auto-pilot can be called from the Flask API (single-shot) or
from `main.py autopilot` mode (continuous loop).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

from ..db import init_db, list_tasks, get_daily_revenue, get_total_metrics
from ..orchestration import assign_task
from ..dispatcher import get_dispatcher
from ..safety import DEFAULT_POLICY
from .ceo_brain import get_brain


@dataclass
class CycleReport:
    cycle_number: int
    started_at: str
    duration_ms: int
    brain_result: dict
    tasks_assigned: int
    tasks_dispatched: int
    tasks_completed: int
    tasks_failed: int
    daily_revenue: float
    errors: list[str] = field(default_factory=list)


class AutoPilot:
    """
    Drives the CEO GIR system through repeated assign→dispatch→evaluate cycles.
    Safe to call from Flask request handlers (single cycle).
    """

    def __init__(self, db_path: str = "ceo_gir.db"):
        self._db_path  = db_path
        self._cycles   = 0
        self._running  = False

    def run_cycle(self) -> CycleReport:
        """Execute one full cycle. Thread-safe — each call opens its own connection."""
        self._cycles += 1
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        t0 = time.monotonic()
        errors = []

        conn = init_db(self._db_path)
        try:
            brain = get_brain()
            brain_result = brain.run_cycle(conn)

            # Assign all queued tasks
            assigned_count = 0
            queued = list_tasks(conn, status="queued", limit=30)
            for task in queued:
                try:
                    result = assign_task(conn, task["task_id"], policy=DEFAULT_POLICY)
                    if result["status"] in ("assigned", "blocked_approval"):
                        assigned_count += 1
                except Exception as e:
                    errors.append(f"assign {task['task_id'][:8]}: {e}")
            conn.commit()

            # Dispatch all assigned tasks
            assigned = list_tasks(conn, status="assigned", limit=20)
            dispatcher = get_dispatcher()
            dispatch_results = dispatcher.dispatch_batch(conn, assigned)

            completed = sum(1 for r in dispatch_results if r.get("status") == "completed")
            failed    = sum(1 for r in dispatch_results if r.get("status") == "failed")

            daily_revenue = get_daily_revenue(conn)

        except Exception as e:
            errors.append(f"cycle error: {e}")
            completed = failed = assigned_count = 0
            daily_revenue = 0.0
            brain_result = {}
        finally:
            conn.close()

        duration_ms = int((time.monotonic() - t0) * 1000)
        return CycleReport(
            cycle_number=self._cycles,
            started_at=started_at,
            duration_ms=duration_ms,
            brain_result=brain_result,
            tasks_assigned=assigned_count,
            tasks_dispatched=len(dispatch_results) if "dispatch_results" in dir() else 0,
            tasks_completed=completed,
            tasks_failed=failed,
            daily_revenue=daily_revenue,
            errors=errors,
        )

    def seed(self) -> dict:
        """Seed all pipelines via CEO Brain. Safe to call once at startup."""
        conn = init_db(self._db_path)
        try:
            result = get_brain().seed_all_pipelines(conn)
            return result
        finally:
            conn.close()

    def run_continuous(self, cycles: int = 10, delay_seconds: float = 2.0, on_cycle=None) -> list[CycleReport]:
        """
        Run N cycles with a delay between each. Calls on_cycle(report) if provided.
        Used by `main.py autopilot` mode.
        """
        self._running = True
        reports = []
        try:
            for i in range(cycles):
                if not self._running:
                    break
                report = self.run_cycle()
                reports.append(report)
                if on_cycle:
                    on_cycle(report)
                if i < cycles - 1:
                    time.sleep(delay_seconds)
        finally:
            self._running = False
        return reports

    def stop(self):
        self._running = False

    @property
    def cycle_count(self) -> int:
        return self._cycles


def cycle_report_to_dict(r: CycleReport) -> dict:
    return {
        "cycle_number": r.cycle_number,
        "started_at": r.started_at,
        "duration_ms": r.duration_ms,
        "brain": r.brain_result,
        "tasks_assigned": r.tasks_assigned,
        "tasks_dispatched": r.tasks_dispatched,
        "tasks_completed": r.tasks_completed,
        "tasks_failed": r.tasks_failed,
        "daily_revenue": r.daily_revenue,
        "errors": r.errors,
    }


# Module-level singleton keyed by db path
_pilots: dict[str, AutoPilot] = {}


def get_auto_pilot(db_path: str = "ceo_gir.db") -> AutoPilot:
    if db_path not in _pilots:
        _pilots[db_path] = AutoPilot(db_path)
    return _pilots[db_path]

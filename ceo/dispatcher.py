"""
CEO GIR Dispatcher — routes tasks to workers, tracks capacity, manages execution.
"""
from __future__ import annotations

import sqlite3
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from .orchestration import claim_task, complete_task, fail_task
from .workstreams.registry import route_task
from .workers.base import WorkerResult
from .economics import calculate_economic_outcome


@dataclass
class WorkerSlot:
    worker_id: str
    workstream_id: str
    busy: bool = False
    current_task_id: Optional[str] = None
    completed_count: int = 0
    failed_count: int = 0
    last_active: float = field(default_factory=time.monotonic)


class Dispatcher:
    """
    Routes assigned tasks to the correct worker, respects capacity limits,
    and records outcomes back to the DB.
    """

    def __init__(self, max_concurrent: int = 4):
        self._slots: dict[str, WorkerSlot] = {}
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()

    def available_slots(self) -> int:
        with self._lock:
            busy = sum(1 for s in self._slots.values() if s.busy)
            return max(0, self._max_concurrent - busy)

    def dispatch(self, conn: sqlite3.Connection, task: dict) -> dict:
        """
        Dispatch a single assigned task synchronously.
        Returns the dispatch result dict.
        """
        task_id = task["task_id"]
        agent_id = f"worker:{task.get('workstream_id', 'general')}"

        # Claim the task (moves assigned → in_progress)
        try:
            claim_task(conn, task_id, agent_id)
        except Exception as e:
            return {"task_id": task_id, "status": "error", "error": str(e)}

        worker = route_task(task)
        if worker is None:
            fail_task(conn, task_id, error="no worker found for task capabilities")
            return {"task_id": task_id, "status": "failed", "reason": "no_worker"}

        slot = self._acquire_slot(agent_id, task.get("workstream_id", "general"), task_id)
        try:
            result: WorkerResult = worker.execute(task)
        except Exception as exc:
            self._release_slot(slot, success=False)
            fail_task(conn, task_id, error=str(exc))
            return {"task_id": task_id, "status": "failed", "reason": str(exc)}

        self._release_slot(slot, success=result.success)

        if result.success:
            complete_task(conn, task_id, output=result.output, duration_ms=result.duration_ms)
            return {
                "task_id": task_id,
                "status": "completed",
                "output": result.output,
                "duration_ms": result.duration_ms,
            }
        else:
            fail_task(conn, task_id, error=result.error or "worker returned failure")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

    def dispatch_batch(self, conn: sqlite3.Connection, tasks: list[dict]) -> list[dict]:
        """Dispatch multiple tasks sequentially, respecting capacity."""
        results = []
        for task in tasks:
            if self.available_slots() == 0:
                results.append({"task_id": task["task_id"], "status": "deferred", "reason": "at_capacity"})
                continue
            result = self.dispatch(conn, task)
            results.append(result)
        conn.commit()
        return results

    def get_worker_stats(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "worker_id": s.worker_id,
                    "workstream_id": s.workstream_id,
                    "busy": s.busy,
                    "current_task_id": s.current_task_id,
                    "completed_count": s.completed_count,
                    "failed_count": s.failed_count,
                    "idle_seconds": round(time.monotonic() - s.last_active, 1),
                }
                for s in self._slots.values()
            ]

    def _acquire_slot(self, agent_id: str, workstream_id: str, task_id: str) -> WorkerSlot:
        with self._lock:
            if agent_id not in self._slots:
                self._slots[agent_id] = WorkerSlot(
                    worker_id=agent_id, workstream_id=workstream_id
                )
            slot = self._slots[agent_id]
            slot.busy = True
            slot.current_task_id = task_id
            slot.last_active = time.monotonic()
            return slot

    def _release_slot(self, slot: WorkerSlot, success: bool) -> None:
        with self._lock:
            slot.busy = False
            slot.current_task_id = None
            slot.last_active = time.monotonic()
            if success:
                slot.completed_count += 1
            else:
                slot.failed_count += 1


# Module-level singleton
_default_dispatcher: Optional[Dispatcher] = None


def get_dispatcher() -> Dispatcher:
    global _default_dispatcher
    if _default_dispatcher is None:
        _default_dispatcher = Dispatcher()
    return _default_dispatcher

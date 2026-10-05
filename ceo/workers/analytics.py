"""
Analytics Worker — aggregates performance metrics, detects trends, generates insights.
"""
from __future__ import annotations
import time
import sqlite3
from .base import BaseWorker, WorkerResult


class PerformanceAnalyticsWorker(BaseWorker):
    capabilities = ["analytics", "reporting", "metrics", "performance"]
    workstream_id = "research"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)

        workstream_id = input_data.get("workstream_id")
        period_days = int(input_data.get("period_days", 7))
        conn = input_data.get("_conn")  # injected by dispatcher when available

        if conn:
            report = self._build_report_from_db(conn, workstream_id, period_days)
        else:
            report = self._build_mock_report(workstream_id, period_days)

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"analytics_report": report},
            duration_ms=duration_ms,
        )

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data

    def _build_report_from_db(self, conn: sqlite3.Connection, workstream_id: str, period_days: int) -> dict:
        where = ""
        params = [period_days]
        if workstream_id:
            where = "AND t.workstream_id = ?"
            params.append(workstream_id)

        rows = conn.execute(
            f"""
            SELECT
                t.workstream_id,
                COUNT(*) as total_tasks,
                SUM(CASE WHEN t.status='completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN t.status='failed' THEN 1 ELSE 0 END) as failed,
                AVG(CASE WHEN r.revenue IS NOT NULL THEN r.revenue ELSE 0 END) as avg_revenue
            FROM ceo_tasks t
            LEFT JOIN ceo_opportunity_outcomes r ON t.opportunity_id = r.opportunity_id
            WHERE t.created_at >= datetime('now', ? || ' days') {where}
            GROUP BY t.workstream_id
            """,
            params,
        ).fetchall()

        workstreams = []
        for row in rows:
            d = dict(row)
            d["completion_rate"] = round(d["completed"] / d["total_tasks"], 2) if d["total_tasks"] > 0 else 0
            workstreams.append(d)

        return {
            "period_days": period_days,
            "workstreams": workstreams,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _build_mock_report(self, workstream_id: str, period_days: int) -> dict:
        return {
            "period_days": period_days,
            "workstream_id": workstream_id,
            "total_tasks": 12,
            "completed": 9,
            "failed": 1,
            "in_progress": 2,
            "completion_rate": 0.75,
            "avg_revenue": 0.0,
            "top_performers": [],
            "recommendations": [
                "Increase task priority for high-ROI workstreams",
                "Review failed tasks for common failure patterns",
                "Consider parallel execution for independent tasks",
            ],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }


class RevenueAnalyticsWorker(BaseWorker):
    capabilities = ["revenue_analytics", "financial_reporting", "kpi"]
    workstream_id = "research"

    def execute(self, task: dict) -> WorkerResult:
        start = time.monotonic()
        input_data = self._parse_input(task)
        conn = input_data.get("_conn")

        if conn:
            report = self._build_revenue_report(conn)
        else:
            report = self._build_mock_revenue_report()

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkerResult(
            success=True,
            output={"revenue_report": report},
            duration_ms=duration_ms,
        )

    def _parse_input(self, task: dict) -> dict:
        data = task.get("input_json") or {}
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except Exception:
                return {}
        return data

    def _build_revenue_report(self, conn: sqlite3.Connection) -> dict:
        daily_rows = conn.execute(
            """
            SELECT date(recorded_at) as day, SUM(metric_value) as revenue
            FROM ceo_metric_observations
            WHERE metric_name LIKE '%revenue%'
              AND recorded_at >= datetime('now', '-30 days')
            GROUP BY day ORDER BY day DESC LIMIT 30
            """
        ).fetchall()

        daily = [{"day": r["day"], "revenue": r["revenue"]} for r in daily_rows]
        total = sum(r["revenue"] for r in daily)

        return {
            "daily": daily,
            "total_30d": round(total, 2),
            "avg_daily": round(total / 30, 2),
            "milestones": self._compute_milestones(total / 30),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _build_mock_revenue_report(self) -> dict:
        return {
            "daily": [],
            "total_30d": 0.0,
            "avg_daily": 0.0,
            "milestones": self._compute_milestones(0.0),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _compute_milestones(self, avg_daily: float) -> list[dict]:
        targets = [5, 10, 20, 50, 100]
        return [
            {
                "target": t,
                "achieved": avg_daily >= t,
                "progress_pct": min(100, round(avg_daily / t * 100, 1)),
            }
            for t in targets
        ]

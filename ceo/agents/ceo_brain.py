"""
CEO Brain — autonomous decision engine.

Every cycle it:
  1. Reads current system state
  2. Decides which workstreams need attention
  3. Creates the next task in each workstream's profit pipeline
  4. Evaluates completed tasks and spawns follow-ups
  5. Records revenue from completed revenue-generating tasks

Profit pipeline per workstream:
  etsy:      trend_research → niche_analysis → asset_creation → listing → sales_tracking → optimize
  fiverr:    trend_research → gig_creation → delivery → sales_tracking → optimize
  affiliate: trend_research → content_creation → seo → email_capture → email_campaign → analytics
  youtube:   trend_research → content_script → thumbnail → distribute → analytics → optimize
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

from ..db import (
    list_tasks, get_memories, record_metric,
    get_total_metrics, get_daily_revenue,
)
from ..orchestration import create_and_queue_task
from ..learning import learn_from_completion, EVAL_SCALED, EVAL_VALIDATED
from ..replanning import determine_next_action, replan_after_evaluation
from ..economics import EconomicOutcome, calculate_economic_outcome


# ── Pipeline definitions ──────────────────────────────────────────────────
# Each step is (title_template, capabilities, input_data_fn, workstream_id)

def _etsy_pipeline(niche: str = "boho", product_type: str = "printable") -> list[dict]:
    return [
        {
            "title": f"Trend research: Etsy {product_type} niches",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 3,
            "input_data": {"platform": "etsy", "top_n": 3},
        },
        {
            "title": f"Niche analysis: {niche} {product_type}s",
            "workstream_id": "research",
            "capabilities": ["niche_analysis"],
            "priority": 3,
            "input_data": {"niche": niche, "platform": "etsy", "product_type": product_type},
        },
        {
            "title": f"Create {niche} {product_type} asset pack",
            "workstream_id": "assets",
            "capabilities": ["asset_creation"],
            "priority": 4,
            "input_data": {"asset_type": product_type, "style": niche, "format": "pdf"},
        },
        {
            "title": f"Create Etsy listing: {niche} {product_type}",
            "workstream_id": "etsy",
            "capabilities": ["listing", "etsy"],
            "priority": 4,
            "input_data": {"product_type": product_type, "niche": niche, "price_usd": 4.99},
        },
        {
            "title": f"Track Etsy sales: {niche} {product_type}",
            "workstream_id": "etsy",
            "capabilities": ["sales_tracking"],
            "priority": 5,
            "input_data": {"platform": "etsy", "niche": niche, "tracking_days": 7},
        },
        {
            "title": f"Optimize Etsy listing: {niche} {product_type}",
            "workstream_id": "optimization",
            "capabilities": ["pricing", "optimization"],
            "priority": 5,
            "input_data": {"platform": "etsy", "current_price": 4.99, "product_type": product_type},
        },
    ]


def _fiverr_pipeline(service: str = "thumbnail_design") -> list[dict]:
    return [
        {
            "title": f"Trend research: Fiverr {service} demand",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 3,
            "input_data": {"platform": "fiverr", "top_n": 3},
        },
        {
            "title": f"Create Fiverr gig: {service}",
            "workstream_id": "fiverr",
            "capabilities": ["freelance", "fiverr"],
            "priority": 3,
            "input_data": {"service_type": service, "tier": "basic", "price_usd": 15.0},
        },
        {
            "title": f"Fulfill Fiverr orders: {service}",
            "workstream_id": "fiverr",
            "capabilities": ["service_delivery"],
            "priority": 4,
            "input_data": {"service_type": service, "order_count": 2, "price_per": 15.0},
        },
        {
            "title": f"Track Fiverr gig performance: {service}",
            "workstream_id": "analytics",
            "capabilities": ["sales_tracking"],
            "priority": 5,
            "input_data": {"platform": "fiverr", "service": service, "tracking_days": 7},
        },
    ]


def _affiliate_pipeline(niche: str = "tech") -> list[dict]:
    return [
        {
            "title": f"Trend research: affiliate {niche} programs",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 2,
            "input_data": {"platform": "affiliate", "top_n": 3},
        },
        {
            "title": f"Create affiliate content: {niche}",
            "workstream_id": "affiliate",
            "capabilities": ["affiliate", "marketing"],
            "priority": 3,
            "input_data": {"niche": niche, "content_format": "comparison"},
        },
        {
            "title": f"SEO optimize: {niche} affiliate content",
            "workstream_id": "seo",
            "capabilities": ["seo", "content_optimization"],
            "priority": 4,
            "input_data": {"topic": f"best {niche} products", "target_keyword": f"best {niche}"},
        },
        {
            "title": f"Build email list: {niche} lead magnet",
            "workstream_id": "affiliate",
            "capabilities": ["list_building"],
            "priority": 4,
            "input_data": {"niche": niche, "lead_magnet": "free_guide", "traffic_source": "organic"},
        },
        {
            "title": f"Email campaign: {niche} affiliate promo",
            "workstream_id": "affiliate",
            "capabilities": ["email_campaign"],
            "priority": 5,
            "input_data": {"campaign_type": "promotional", "list_size": 200, "niche": niche},
        },
    ]


def _youtube_pipeline(topic: str = "ai tools") -> list[dict]:
    return [
        {
            "title": f"Trend research: YouTube/TikTok {topic}",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 2,
            "input_data": {"platform": "youtube", "top_n": 3},
        },
        {
            "title": f"Script content: {topic} video",
            "workstream_id": "content",
            "capabilities": ["content", "writing"],
            "priority": 3,
            "input_data": {"content_type": "short_form", "topic": topic},
        },
        {
            "title": f"Create thumbnail: {topic}",
            "workstream_id": "assets",
            "capabilities": ["content_assets", "thumbnails"],
            "priority": 3,
            "input_data": {"content_type": "thumbnail", "platform": "youtube", "topic": topic},
        },
        {
            "title": f"Distribute: {topic} across platforms",
            "workstream_id": "youtube",
            "capabilities": ["social_media", "distribution"],
            "priority": 4,
            "input_data": {"platforms": ["youtube", "tiktok", "instagram"], "topic": topic, "content_type": "short_form"},
        },
        {
            "title": f"Analytics: {topic} performance",
            "workstream_id": "analytics",
            "capabilities": ["analytics", "reporting"],
            "priority": 5,
            "input_data": {"workstream_id": "youtube", "period_days": 7},
        },
    ]


# ── Pipeline catalog ──────────────────────────────────────────────────────
PIPELINES = {
    "etsy_boho":       lambda: _etsy_pipeline("boho", "printable"),
    "etsy_minimal":    lambda: _etsy_pipeline("minimal", "printable"),
    "etsy_celestial":  lambda: _etsy_pipeline("celestial", "printable"),
    "etsy_planner":    lambda: _etsy_pipeline("minimal", "planner"),
    "etsy_svg":        lambda: _etsy_pipeline("wildflower", "svg"),
    "fiverr_thumb":    lambda: _fiverr_pipeline("thumbnail_design"),
    "fiverr_logo":     lambda: _fiverr_pipeline("logo_design"),
    "fiverr_video":    lambda: _fiverr_pipeline("video_editing"),
    "fiverr_content":  lambda: _fiverr_pipeline("content_writing"),
    "affiliate_tech":  lambda: _affiliate_pipeline("tech"),
    "affiliate_finance": lambda: _affiliate_pipeline("finance"),
    "affiliate_fitness": lambda: _affiliate_pipeline("fitness"),
    "youtube_ai":      lambda: _youtube_pipeline("ai tools"),
    "youtube_hustle":  lambda: _youtube_pipeline("side hustle"),
    "youtube_finance": lambda: _youtube_pipeline("personal finance"),
}

# Revenue targets per workstream (daily $)
WORKSTREAM_TARGETS = {
    "etsy":      20.0,
    "fiverr":    15.0,
    "affiliate": 25.0,
    "youtube":   20.0,
}

# How many parallel pipelines per workstream to run
WORKSTREAM_PARALLELISM = {
    "etsy":      3,
    "fiverr":    2,
    "affiliate": 2,
    "youtube":   2,
}


class CEOBrain:
    """Autonomous decision engine — one instance drives the whole system."""

    def __init__(self, min_tasks_per_workstream: int = 2):
        self._min_tasks = min_tasks_per_workstream

    def run_cycle(self, conn: sqlite3.Connection) -> dict:
        """
        One full decision cycle. Returns a summary of what was decided.
        """
        cycle_start = time.monotonic()
        created_tasks = []
        evaluated_tasks = []
        revenue_recorded = 0.0

        # 1. Evaluate completed tasks and record revenue
        completed = list_tasks(conn, status="completed", limit=50)
        for task in completed:
            if task.get("result_json"):
                rev = self._extract_revenue(task)
                if rev > 0:
                    record_metric(
                        conn,
                        metric_name="task_revenue",
                        metric_value=rev,
                        task_id=task["task_id"],
                        workstream_id=task.get("workstream_id"),
                        context={"source": "worker_output"},
                    )
                    revenue_recorded += rev

        # 2. Assess workstream health — how many active tasks per workstream?
        active_by_ws = self._count_active_by_workstream(conn)

        # 3. Decide which workstreams need new pipelines
        daily_revenue = get_daily_revenue(conn)
        metrics       = get_total_metrics(conn)

        for ws_id, target in WORKSTREAM_TARGETS.items():
            current_active = active_by_ws.get(ws_id, 0) + active_by_ws.get("research", 0)
            desired = WORKSTREAM_PARALLELISM.get(ws_id, 2)

            if current_active >= desired * 4:
                continue  # workstream fully loaded

            pipelines_for_ws = [k for k in PIPELINES if k.startswith(ws_id)]
            pipelines_to_add = max(0, desired - (current_active // 4))

            for pipeline_key in pipelines_for_ws[:pipelines_to_add]:
                tasks = PIPELINES[pipeline_key]()
                for step in tasks:
                    # Avoid duplicates: skip if same title already queued/assigned
                    existing = conn.execute(
                        "SELECT task_id FROM ceo_tasks WHERE title=? AND status IN ('queued','assigned','in_progress')",
                        (step["title"],),
                    ).fetchone()
                    if existing:
                        continue

                    task_id = create_and_queue_task(
                        conn,
                        title=step["title"],
                        workstream_id=step["workstream_id"],
                        priority=step["priority"],
                        input_data=step["input_data"],
                        required_capabilities=step["capabilities"],
                        created_by="ceo_brain",
                    )
                    created_tasks.append({"task_id": task_id, "title": step["title"]})

        conn.commit()
        duration_ms = int((time.monotonic() - cycle_start) * 1000)

        return {
            "cycle_duration_ms": duration_ms,
            "tasks_created": len(created_tasks),
            "revenue_recorded": round(revenue_recorded, 2),
            "daily_revenue": daily_revenue,
            "created": created_tasks,
        }

    def seed_all_pipelines(self, conn: sqlite3.Connection) -> dict:
        """
        Seed the full pipeline catalog — call once to populate the system with
        a rich initial task set across all workstreams.
        """
        created = []
        for pipeline_key, pipeline_fn in PIPELINES.items():
            tasks = pipeline_fn()
            for step in tasks:
                existing = conn.execute(
                    "SELECT task_id FROM ceo_tasks WHERE title=?",
                    (step["title"],),
                ).fetchone()
                if existing:
                    continue
                task_id = create_and_queue_task(
                    conn,
                    title=step["title"],
                    workstream_id=step["workstream_id"],
                    priority=step["priority"],
                    input_data=step["input_data"],
                    required_capabilities=step["capabilities"],
                    created_by="ceo_seed",
                )
                created.append({"task_id": task_id, "title": step["title"], "pipeline": pipeline_key})
        conn.commit()
        return {"seeded": len(created), "tasks": created}

    def _count_active_by_workstream(self, conn: sqlite3.Connection) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT workstream_id, COUNT(*) as cnt FROM ceo_tasks
            WHERE status IN ('queued','assigned','in_progress')
              AND workstream_id IS NOT NULL
            GROUP BY workstream_id
            """
        ).fetchall()
        return {r["workstream_id"]: r["cnt"] for r in rows}

    def _extract_revenue(self, task: dict) -> float:
        result = task.get("result_json") or {}
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except Exception:
                return 0.0

        # Check economic_data.revenue first
        econ = result.get("economic_data") or {}
        if econ.get("revenue"):
            return float(econ["revenue"])

        # Check nested output keys common in delivery/tracking workers
        for key in ("net_revenue", "projected_revenue", "estimated_monthly_revenue"):
            if result.get(key):
                return float(result[key]) / 30.0  # monthly → daily estimate

        return 0.0


# Module-level singleton
_brain: Optional[CEOBrain] = None


def get_brain() -> CEOBrain:
    global _brain
    if _brain is None:
        _brain = CEOBrain()
    return _brain

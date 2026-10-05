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
from ..intelligence import (
    score_workstreams, persist_scores, load_scores,
    persist_tier_state, load_tier_state,
    get_unlocked_workstreams, get_current_tier, get_next_tier,
    find_clone_candidates, record_intelligence_cycle,
    UNLOCK_TIERS,
)


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


def _asset2d_pipeline(asset_type: str = "printable", style: str = "minimal") -> list[dict]:
    return [
        {
            "title": f"Trend research: 2D {asset_type} market",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 3,
            "input_data": {"platform": "etsy", "asset_type": asset_type, "top_n": 5},
        },
        {
            "title": f"Generate {style} {asset_type} asset pack",
            "workstream_id": "assets_2d",
            "capabilities": ["2d_asset", "design"],
            "priority": 4,
            "input_data": {"asset_type": asset_type, "style": style, "quantity": 3},
        },
        {
            "title": f"List {style} {asset_type} on Etsy",
            "workstream_id": "etsy",
            "capabilities": ["listing", "etsy"],
            "priority": 4,
            "input_data": {"product_type": asset_type, "niche": style, "price_usd": 6.99},
        },
        {
            "title": f"List {style} {asset_type} on Creative Market",
            "workstream_id": "assets_2d",
            "capabilities": ["2d_asset"],
            "priority": 3,
            "input_data": {"asset_type": asset_type, "style": style, "platform": "creative_market"},
        },
        {
            "title": f"Track {style} {asset_type} sales performance",
            "workstream_id": "analytics",
            "capabilities": ["analytics", "reporting"],
            "priority": 5,
            "input_data": {"workstream_id": "assets_2d", "asset_type": asset_type, "period_days": 7},
        },
    ]


def _asset3d_pipeline(model_type: str = "3d_model", style: str = "low_poly") -> list[dict]:
    price_map = {"3d_model": 19.99, "game_asset": 14.99, "character": 29.99, "environment": 24.99, "prop": 9.99}
    price = price_map.get(model_type, 19.99)
    return [
        {
            "title": f"Trend research: 3D {model_type} demand",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 3,
            "input_data": {"platform": "cgtrader", "model_type": model_type, "top_n": 5},
        },
        {
            "title": f"Generate {style} {model_type}",
            "workstream_id": "assets_3d",
            "capabilities": ["3d_asset", "3d_model"],
            "priority": 4,
            "input_data": {"model_type": model_type, "style": style, "textured": True, "rigged": model_type == "character"},
        },
        {
            "title": f"List {style} {model_type} on CGTrader",
            "workstream_id": "assets_3d",
            "capabilities": ["3d_asset"],
            "priority": 4,
            "input_data": {"model_type": model_type, "style": style, "platform": "cgtrader", "price_usd": price},
        },
        {
            "title": f"List {style} {model_type} on TurboSquid",
            "workstream_id": "assets_3d",
            "capabilities": ["3d_asset"],
            "priority": 4,
            "input_data": {"model_type": model_type, "style": style, "platform": "turbosquid", "price_usd": price},
        },
        {
            "title": f"Track 3D {model_type} sales: {style}",
            "workstream_id": "analytics",
            "capabilities": ["analytics", "reporting"],
            "priority": 5,
            "input_data": {"workstream_id": "assets_3d", "model_type": model_type, "period_days": 7},
        },
    ]


def _shorts_pipeline(niche: str = "ai_tips", topic: str = "") -> list[dict]:
    """YouTube Shorts pipeline — free: gTTS + Pollinations + YouTube API."""
    return [
        {
            "title": f"Research trending {niche} topics for Shorts",
            "workstream_id": "research",
            "capabilities": ["trend_research"],
            "priority": 2,
            "input_data": {"platform": "youtube", "niche": niche, "format": "shorts"},
        },
        {
            "title": f"Create YouTube Short: {niche}{' — ' + topic if topic else ''}",
            "workstream_id": "youtube",
            "capabilities": ["youtube_shorts", "video_content"],
            "priority": 3,
            "input_data": {"niche": niche, "topic": topic or None},
        },
        {
            "title": f"Track YouTube Short performance: {niche}",
            "workstream_id": "analytics",
            "capabilities": ["analytics", "reporting"],
            "priority": 5,
            "input_data": {"platform": "youtube", "niche": niche, "period_days": 7},
        },
    ]


def _gumroad_pipeline(asset_type: str = "printable", style: str = "minimal") -> list[dict]:
    """Free digital product pipeline: generate → post to Gumroad (free, 10% cut)."""
    price_map = {"printable": 4.99, "logo": 14.99, "svg_bundle": 8.99, "template": 9.99, "planner": 6.99}
    price = price_map.get(asset_type, 4.99)
    return [
        {
            "title": f"Generate {style} {asset_type} for Gumroad",
            "workstream_id": "assets_2d",
            "capabilities": ["2d_asset", "design"],
            "priority": 3,
            "input_data": {"asset_type": asset_type, "style": style, "quantity": 1},
        },
        {
            "title": f"Post {style} {asset_type} to Gumroad",
            "workstream_id": "gumroad",
            "capabilities": ["2d_asset", "design", "printable"],
            "priority": 3,
            "input_data": {
                "asset_type": asset_type,
                "style": style,
                "price_usd": price,
                "platform": "gumroad",
            },
        },
        {
            "title": f"Track Gumroad sales: {style} {asset_type}",
            "workstream_id": "analytics",
            "capabilities": ["analytics"],
            "priority": 5,
            "input_data": {"platform": "gumroad", "asset_type": asset_type, "period_days": 7},
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
    # 2D Asset pipelines
    "2d_printable_boho":     lambda: _asset2d_pipeline("printable", "boho"),
    "2d_printable_minimal":  lambda: _asset2d_pipeline("printable", "minimal"),
    "2d_svg_wildflower":     lambda: _asset2d_pipeline("svg_bundle", "wildflower"),
    "2d_logo_corporate":     lambda: _asset2d_pipeline("logo", "corporate"),
    "2d_template_social":    lambda: _asset2d_pipeline("template", "minimal"),
    "2d_planner_pastel":     lambda: _asset2d_pipeline("planner", "pastel"),
    # 3D Asset pipelines
    "3d_lowpoly_prop":       lambda: _asset3d_pipeline("prop", "low_poly"),
    "3d_lowpoly_env":        lambda: _asset3d_pipeline("environment", "low_poly"),
    "3d_character_fantasy":  lambda: _asset3d_pipeline("character", "fantasy"),
    "3d_scifi_model":        lambda: _asset3d_pipeline("3d_model", "sci_fi"),
    "3d_game_asset_cartoon": lambda: _asset3d_pipeline("game_asset", "cartoon"),
    # YouTube Shorts pipelines (free — gTTS + Pollinations + YouTube API)
    "shorts_ai_tips":        lambda: _shorts_pipeline("ai_tips"),
    "shorts_gaming":         lambda: _shorts_pipeline("trending_gaming"),
    "shorts_money":          lambda: _shorts_pipeline("money_tips"),
    "shorts_facts":          lambda: _shorts_pipeline("facts"),
    # Gumroad free store pipelines
    "gumroad_printable_boho":    lambda: _gumroad_pipeline("printable", "boho"),
    "gumroad_printable_minimal": lambda: _gumroad_pipeline("printable", "minimal"),
    "gumroad_svg_wildflower":    lambda: _gumroad_pipeline("svg_bundle", "wildflower"),
    "gumroad_logo_corporate":    lambda: _gumroad_pipeline("logo", "corporate"),
}

# Revenue targets per workstream (daily $)
WORKSTREAM_TARGETS = {
    "etsy":      20.0,
    "fiverr":    15.0,
    "affiliate": 25.0,
    "youtube":   5.0,   # Shorts take time to grow
    "gumroad":   8.0,
    "assets_2d": 15.0,
    "assets_3d": 25.0,
}

# How many parallel pipelines per workstream to run
WORKSTREAM_PARALLELISM = {
    "etsy":      3,
    "fiverr":    2,
    "affiliate": 2,
    "youtube":   2,
    "assets_2d": 3,
    "assets_3d": 2,
}


class CEOBrain:
    """Autonomous decision engine — one instance drives the whole system."""

    def __init__(self, min_tasks_per_workstream: int = 2):
        self._min_tasks = min_tasks_per_workstream

    def run_cycle(self, conn: sqlite3.Connection) -> dict:
        """
        One full adaptive decision cycle:
          1. Record revenue from completed tasks
          2. Score all workstreams (reinforcement)
          3. Check goal tier / unlock new workstreams
          4. Shift resources: scale winners, throttle underperformers
          5. Clone high-scoring pipelines
          6. Fill gaps in unlocked workstreams
        """
        cycle_start = time.monotonic()
        created_tasks   = []
        revenue_recorded = 0.0
        clones_spawned   = 0

        # ── 1. Revenue harvest ────────────────────────────────────────────
        completed = list_tasks(conn, status="completed", limit=100)
        seen_tasks = set()
        for task in completed:
            if task["task_id"] in seen_tasks:
                continue
            seen_tasks.add(task["task_id"])
            if task.get("result_json"):
                rev = self._extract_revenue(task)
                if rev > 0:
                    # Only record once — check if already recorded
                    already = conn.execute(
                        "SELECT obs_id FROM ceo_metric_observations WHERE task_id=? AND metric_name='task_revenue'",
                        (task["task_id"],),
                    ).fetchone()
                    if not already:
                        record_metric(
                            conn,
                            metric_name="task_revenue",
                            metric_value=rev,
                            task_id=task["task_id"],
                            workstream_id=task.get("workstream_id"),
                            context={"source": "worker_output"},
                        )
                        revenue_recorded += rev

        # ── 2. Score workstreams ──────────────────────────────────────────
        scores = score_workstreams(conn)
        persist_scores(conn, scores)

        # ── 3. Goal tier check ────────────────────────────────────────────
        daily_revenue = get_daily_revenue(conn)
        tier_state    = persist_tier_state(conn, daily_revenue)
        unlocked_ws   = get_unlocked_workstreams(daily_revenue)

        # ── 4. Adaptive parallelism: winners get more slots ───────────────
        active_by_ws  = self._count_active_by_workstream(conn)
        parallelism   = dict(WORKSTREAM_PARALLELISM)  # start with defaults

        for ws_id, score in scores.items():
            if score.recommendation == "scale":
                parallelism[ws_id] = parallelism.get(ws_id, 2) + 2
            elif score.recommendation == "pause":
                parallelism[ws_id] = max(0, parallelism.get(ws_id, 2) - 1)
            elif score.recommendation == "investigate":
                parallelism[ws_id] = max(1, parallelism.get(ws_id, 2) - 1)

        # ── 5. Clone high-scoring pipelines ──────────────────────────────
        candidates = find_clone_candidates(conn, scores, min_score=65.0)
        for candidate in candidates[:3]:  # max 3 clones per cycle
            ws_id = candidate.workstream_id
            matching_pipelines = [k for k in PIPELINES if k.startswith(ws_id) or k.startswith(ws_id.replace("_", ""))]
            for pk in matching_pipelines[:1]:
                tasks = PIPELINES[pk]()
                cloned = False
                for step in tasks:
                    title_variant = f"[SCALED] {step['title']}"
                    existing = conn.execute(
                        "SELECT task_id FROM ceo_tasks WHERE title=? AND status IN ('queued','assigned','in_progress')",
                        (title_variant,),
                    ).fetchone()
                    if existing:
                        continue
                    create_and_queue_task(
                        conn,
                        title=title_variant,
                        workstream_id=step["workstream_id"],
                        priority=max(1, step["priority"] - 1),  # higher priority
                        input_data=step["input_data"],
                        required_capabilities=step["capabilities"],
                        created_by="ceo_brain_clone",
                    )
                    cloned = True
                if cloned:
                    clones_spawned += 1

        # ── 6. Fill gaps in unlocked workstreams ──────────────────────────
        for ws_id in WORKSTREAM_TARGETS:
            # Skip locked workstreams
            if ws_id not in unlocked_ws:
                continue

            # Skip paused workstreams (unless they have zero tasks ever — then try once)
            ws_score = scores.get(ws_id)
            if ws_score and ws_score.recommendation == "pause" and ws_score.total_tasks > 5:
                continue

            current_active = active_by_ws.get(ws_id, 0)
            desired        = parallelism.get(ws_id, 2)

            if current_active >= desired * 4:
                continue

            pipelines_for_ws = [k for k in PIPELINES if k.startswith(ws_id.replace("_", "")[:6])]
            pipelines_to_add = max(0, desired - (current_active // max(1, len(pipelines_for_ws))))

            for pipeline_key in pipelines_for_ws[:pipelines_to_add]:
                tasks = PIPELINES[pipeline_key]()
                for step in tasks:
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

        # ── 7. Record intelligence cycle ──────────────────────────────────
        record_intelligence_cycle(conn, daily_revenue, scores, clones_spawned, tier_state)
        conn.commit()

        duration_ms = int((time.monotonic() - cycle_start) * 1000)
        return {
            "cycle_duration_ms":  duration_ms,
            "tasks_created":      len(created_tasks),
            "clones_spawned":     clones_spawned,
            "revenue_recorded":   round(revenue_recorded, 2),
            "daily_revenue":      daily_revenue,
            "current_tier":       tier_state.get("tier_label", "Bootstrap"),
            "next_tier":          tier_state.get("next_tier_label"),
            "next_tier_target":   tier_state.get("next_tier_target"),
            "progress_pct":       tier_state.get("progress_pct", 0),
            "unlocked_workstreams": sorted(unlocked_ws),
            "top_workstreams":    [
                {"ws": s.workstream_id, "score": s.score, "rec": s.recommendation}
                for s in sorted(scores.values(), key=lambda x: x.score, reverse=True)[:5]
            ],
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

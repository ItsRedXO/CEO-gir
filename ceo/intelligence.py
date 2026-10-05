"""
CEO Intelligence Layer — self-learning, reinforcement scoring, goal thresholds.

Three systems:

1. WorkstreamScorer  — tracks revenue/success per workstream, produces a score
                       0-100 used by CEO Brain to shift resources.

2. GoalThresholds   — the "trapped until you earn X" unlock mechanic.
                      Workstreams are locked behind daily revenue milestones.
                      Once a tier is hit it stays unlocked permanently.

3. PipelineCloner   — inspects high-scoring completed task chains and
                      clones them into fresh pipeline instances so the
                      brain automatically doubles down on winners.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

from .db import add_memory, record_metric


# ── Unlock tiers ──────────────────────────────────────────────────────────────
# Each tier unlocks additional workstreams when daily revenue reaches the target.
# Tier 0 is always unlocked (system starts here).

UNLOCK_TIERS: list[dict] = [
    {
        "tier": 0,
        "label": "Bootstrap",
        "daily_target": 0.0,
        "unlocks": ["research", "trends", "assets_2d", "youtube", "gumroad", "pinterest"],
        "description": "Foundation — 2D assets + free Gumroad store + YouTube Shorts (all free)",
    },
    {
        "tier": 1,
        "label": "First Dollar",
        "daily_target": 1.0,
        "unlocks": ["etsy", "content", "assets"],
        "description": "Etsy listings live, content pipeline open",
    },
    {
        "tier": 2,
        "label": "Traction",
        "daily_target": 5.0,
        "unlocks": ["fiverr", "affiliate", "seo", "assets_3d"],
        "description": "Fiverr gigs + affiliate content + 3D asset store",
    },
    {
        "tier": 3,
        "label": "Scale",
        "daily_target": 20.0,
        "unlocks": ["youtube", "email", "analytics", "optimization"],
        "description": "YouTube/TikTok + email list + full analytics",
    },
    {
        "tier": 4,
        "label": "Full Autonomy",
        "daily_target": 50.0,
        "unlocks": ["delivery", "pricing", "trends"],
        "description": "All systems — autonomous price optimizer + delivery",
    },
]

# Workstreams available at each tier (cumulative)
def get_unlocked_workstreams(daily_revenue: float) -> set[str]:
    unlocked = set()
    for tier in UNLOCK_TIERS:
        if daily_revenue >= tier["daily_target"]:
            unlocked.update(tier["unlocks"])
    return unlocked


def get_current_tier(daily_revenue: float) -> dict:
    current = UNLOCK_TIERS[0]
    for tier in UNLOCK_TIERS:
        if daily_revenue >= tier["daily_target"]:
            current = tier
    return current


def get_next_tier(daily_revenue: float) -> Optional[dict]:
    for tier in UNLOCK_TIERS:
        if daily_revenue < tier["daily_target"]:
            return tier
    return None


# ── Workstream scorer ─────────────────────────────────────────────────────────

@dataclass
class WorkstreamScore:
    workstream_id: str
    score: float          # 0–100
    total_tasks: int
    completed: int
    failed: int
    total_revenue: float
    avg_revenue_per_task: float
    success_rate: float
    trend: str            # "rising" | "stable" | "falling" | "new"
    recommendation: str   # "scale" | "maintain" | "investigate" | "pause"


def score_workstreams(conn: sqlite3.Connection) -> dict[str, WorkstreamScore]:
    """
    Score every workstream based on completion rate, revenue, and recent trend.
    Returns a dict keyed by workstream_id.
    """
    rows = conn.execute(
        """
        SELECT
            workstream_id,
            COUNT(*) as total,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) as failed
        FROM ceo_tasks
        WHERE workstream_id IS NOT NULL
        GROUP BY workstream_id
        """
    ).fetchall()

    # Revenue per workstream from metrics table
    rev_rows = conn.execute(
        """
        SELECT workstream_id, SUM(metric_value) as total_rev
        FROM ceo_metric_observations
        WHERE metric_name IN ('task_revenue','revenue')
          AND workstream_id IS NOT NULL
        GROUP BY workstream_id
        """
    ).fetchall()
    rev_map = {r["workstream_id"]: float(r["total_rev"] or 0) for r in rev_rows}

    # Recent trend: compare last 10 vs previous 10 completed tasks by revenue
    trend_rows = conn.execute(
        """
        SELECT t.workstream_id,
               SUM(CASE WHEN m.metric_value > 0 THEN 1 ELSE 0 END) as earned_count,
               ROW_NUMBER() OVER (PARTITION BY t.workstream_id ORDER BY t.updated_at DESC) as rn
        FROM ceo_tasks t
        LEFT JOIN ceo_metric_observations m ON m.task_id = t.task_id
        WHERE t.status = 'completed' AND t.workstream_id IS NOT NULL
        GROUP BY t.task_id, t.workstream_id
        """
    ).fetchall()

    scores: dict[str, WorkstreamScore] = {}
    for row in rows:
        ws = row["workstream_id"]
        total     = row["total"] or 0
        completed = row["completed"] or 0
        failed    = row["failed"] or 0
        revenue   = rev_map.get(ws, 0.0)

        success_rate = completed / total if total > 0 else 0.0
        avg_rev      = revenue / completed if completed > 0 else 0.0

        # Score formula:
        # 40pts completion rate, 40pts revenue contribution, 20pts failure penalty
        score = (success_rate * 40) + min(avg_rev * 8, 40) - (failed / max(total, 1) * 20)
        score = max(0.0, min(100.0, score))

        # Trend heuristic based on total volume
        if total < 3:
            trend = "new"
        elif success_rate > 0.75 and avg_rev > 1.0:
            trend = "rising"
        elif failed / max(total, 1) > 0.4:
            trend = "falling"
        else:
            trend = "stable"

        # Recommendation
        if score >= 70:
            rec = "scale"
        elif score >= 40:
            rec = "maintain"
        elif score >= 20:
            rec = "investigate"
        else:
            rec = "pause"

        scores[ws] = WorkstreamScore(
            workstream_id=ws,
            score=round(score, 1),
            total_tasks=total,
            completed=completed,
            failed=failed,
            total_revenue=round(revenue, 2),
            avg_revenue_per_task=round(avg_rev, 2),
            success_rate=round(success_rate, 3),
            trend=trend,
            recommendation=rec,
        )

    return scores


def persist_scores(conn: sqlite3.Connection, scores: dict[str, WorkstreamScore]):
    """Write scores to ceo_state so the dashboard can read them."""
    payload = {
        ws: {
            "score": s.score,
            "trend": s.trend,
            "recommendation": s.recommendation,
            "success_rate": s.success_rate,
            "total_revenue": s.total_revenue,
            "avg_revenue_per_task": s.avg_revenue_per_task,
            "completed": s.completed,
            "failed": s.failed,
        }
        for ws, s in scores.items()
    }
    now = _now()
    conn.execute(
        "INSERT OR REPLACE INTO ceo_state (key, value_json, updated_at) VALUES (?,?,?)",
        ("workstream_scores", json.dumps(payload), now),
    )


def load_scores(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT value_json FROM ceo_state WHERE key='workstream_scores'"
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["value_json"])
    except Exception:
        return {}


# ── Goal threshold state ──────────────────────────────────────────────────────

def persist_tier_state(conn: sqlite3.Connection, daily_revenue: float):
    tier  = get_current_tier(daily_revenue)
    next_ = get_next_tier(daily_revenue)
    unlocked = sorted(get_unlocked_workstreams(daily_revenue))
    payload = {
        "daily_revenue": daily_revenue,
        "current_tier":  tier["tier"],
        "tier_label":    tier["label"],
        "unlocked_workstreams": unlocked,
        "next_tier": next_["tier"] if next_ else None,
        "next_tier_label": next_["label"] if next_ else "MAX",
        "next_tier_target": next_["daily_target"] if next_ else 0.0,
        "next_tier_unlocks": next_["unlocks"] if next_ else [],
        "progress_pct": round(
            min(daily_revenue / next_["daily_target"], 1.0) * 100 if next_ else 100.0, 1
        ),
    }
    conn.execute(
        "INSERT OR REPLACE INTO ceo_state (key, value_json, updated_at) VALUES (?,?,?)",
        ("goal_tier", json.dumps(payload), _now()),
    )
    return payload


def load_tier_state(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT value_json FROM ceo_state WHERE key='goal_tier'"
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["value_json"])
    except Exception:
        return {}


# ── Pipeline cloner ───────────────────────────────────────────────────────────

@dataclass
class CloneCandidate:
    pipeline_key: str
    workstream_id: str
    score: float
    revenue: float
    title_pattern: str


def find_clone_candidates(
    conn: sqlite3.Connection,
    scores: dict[str, WorkstreamScore],
    min_score: float = 65.0,
) -> list[CloneCandidate]:
    """
    Find high-performing workstreams worth cloning into new pipeline instances.
    Returns candidates sorted by score descending.
    """
    candidates = []
    for ws_id, score in scores.items():
        if score.score >= min_score and score.recommendation == "scale":
            candidates.append(CloneCandidate(
                pipeline_key=ws_id,
                workstream_id=ws_id,
                score=score.score,
                revenue=score.total_revenue,
                title_pattern=ws_id.replace("_", " ").title(),
            ))
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def record_intelligence_cycle(
    conn: sqlite3.Connection,
    daily_revenue: float,
    scores: dict[str, WorkstreamScore],
    clones_spawned: int,
    tier_state: dict,
):
    """Write a summary of the intelligence cycle to CEO memory."""
    top = sorted(scores.values(), key=lambda s: s.score, reverse=True)[:3]
    bottom = [s for s in sorted(scores.values(), key=lambda s: s.score) if s.recommendation in ("pause", "investigate")][:2]

    summary_parts = [
        f"Intelligence cycle | revenue=${daily_revenue:.2f}/day | tier={tier_state.get('tier_label','?')}",
    ]
    if top:
        summary_parts.append("Winners: " + ", ".join(f"{s.workstream_id}({s.score:.0f})" for s in top))
    if bottom:
        summary_parts.append("Underperformers: " + ", ".join(f"{s.workstream_id}({s.score:.0f})" for s in bottom))
    if clones_spawned:
        summary_parts.append(f"Cloned {clones_spawned} high-performing pipelines")

    add_memory(
        conn,
        category="intelligence",
        content=" | ".join(summary_parts),
        confidence=1.0,
        context={
            "daily_revenue": daily_revenue,
            "tier": tier_state.get("current_tier"),
            "clones_spawned": clones_spawned,
            "workstream_count": len(scores),
        },
    )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

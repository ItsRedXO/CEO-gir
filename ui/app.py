"""
CEO GIR Dashboard — Flask web UI.
Game-like control panel to visualize and operate the agent ecosystem.
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, abort
from flask_cors import CORS

log = logging.getLogger("ceo_autopilot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_autopilot_thread: threading.Thread | None = None
_autopilot_active = False
_autopilot_interval = int(os.environ.get("CEO_CYCLE_INTERVAL", "30"))
_last_cycle_at: float = 0.0  # epoch seconds


def _autopilot_loop():
    global _autopilot_active
    pilot = get_auto_pilot(DB_PATH)
    while _autopilot_active:
        try:
            conn = init_db(DB_PATH)
            try:
                queued = conn.execute(
                    "SELECT COUNT(*) as n FROM ceo_tasks WHERE status='queued'"
                ).fetchone()["n"]
            finally:
                conn.close()
            if queued == 0:
                log.info("Autopilot: queue empty — seeding pipelines")
                pilot.seed()
            report = pilot.run_cycle()
            _last_cycle_at = time.time()
            log.info(
                "Cycle %d: created=%d dispatched=%d completed=%d rev=$%.2f",
                pilot.cycle_count,
                report.brain_result.get("tasks_created", 0),
                report.tasks_dispatched,
                report.tasks_completed,
                report.daily_revenue,
            )
        except Exception as e:
            log.error("Autopilot error: %s", e)
        # sleep in 0.5s chunks so stop is responsive
        for _ in range(_autopilot_interval * 2):
            if not _autopilot_active:
                break
            time.sleep(0.5)
    log.info("Autopilot loop exited")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ceo.db import (
    init_db, get_task, list_tasks, get_pending_approvals,
    get_total_metrics, get_daily_revenue, get_memories,
    create_task as db_create_task,
)
from ceo.orchestration import (
    assign_task, approve_task, claim_task, complete_task, fail_task,
    create_and_queue_task,
)
from ceo.safety import SafetyPolicy
from ceo.replanning import get_ceo_decision_context, get_next_queued_tasks
from ceo.health import run_health_check, health_to_dict
from ceo.dispatcher import get_dispatcher
from ceo.workstreams.registry import get_workstream_summary
from ceo.agents.ceo_brain import get_brain
from ceo.agents.auto_pilot import get_auto_pilot, cycle_report_to_dict
from ceo.intelligence import (
    load_scores, load_tier_state, score_workstreams,
    persist_scores, persist_tier_state,
    UNLOCK_TIERS,
)

DB_PATH = os.environ.get("CEO_GIR_DB", "ceo_gir.db")
POLICY = SafetyPolicy(
    require_approval_for_side_effects=True,
    max_automated_spend=float(os.environ.get("CEO_MAX_AUTO_SPEND", "5.0")),
)

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)


def get_db():
    return init_db(DB_PATH)


# ── API Routes ─────────────────────────────────────────────────────────────


@app.route("/api/status")
def api_status():
    conn = get_db()
    try:
        metrics = get_total_metrics(conn)
        daily = get_daily_revenue(conn)
        ctx = get_ceo_decision_context(conn)
        blocked = list_tasks(conn, status="blocked_approval", limit=50)
        return jsonify({
            "daily_revenue": daily,
            "total_revenue": metrics["total_revenue"],
            "total_profit": metrics["total_profit"],
            "total_spend": metrics["total_spend"],
            "task_counts": metrics["task_counts"],
            "queued_count": ctx["queued_count"],
            "in_progress_count": ctx["in_progress_count"],
            "blocked_count": ctx["blocked_count"],
            "pending_approvals": len(blocked),
            "memory_count": ctx["memory_count"],
        })
    finally:
        conn.close()


@app.route("/api/tasks")
def api_tasks():
    status = request.args.get("status")
    workstream = request.args.get("workstream")
    conn = get_db()
    try:
        tasks = list_tasks(conn, status=status, workstream_id=workstream, limit=50)
        return jsonify(tasks)
    finally:
        conn.close()


@app.route("/api/tasks/<task_id>")
def api_task_detail(task_id):
    conn = get_db()
    try:
        task = get_task(conn, task_id)
        if not task:
            abort(404)
        approvals = get_pending_approvals(conn, task_id)
        return jsonify({"task": task, "pending_approvals": approvals})
    finally:
        conn.close()


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    data = request.get_json(force=True)
    if not data or not data.get("title"):
        return jsonify({"error": "title required"}), 400
    conn = get_db()
    try:
        task_id = create_and_queue_task(
            conn,
            title=data["title"],
            description=data.get("description", ""),
            workstream_id=data.get("workstream_id"),
            priority=int(data.get("priority", 5)),
            side_effect_type=data.get("side_effect_type"),
            input_data=data.get("input_data"),
            required_capabilities=data.get("required_capabilities"),
            created_by=data.get("created_by", "human"),
        )
        conn.commit()
        return jsonify({"task_id": task_id, "status": "queued"}), 201
    finally:
        conn.close()


@app.route("/api/tasks/<task_id>/assign", methods=["POST"])
def api_assign_task(task_id):
    conn = get_db()
    try:
        result = assign_task(conn, task_id, policy=POLICY)
        conn.commit()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/approvals")
def api_list_approvals():
    conn = get_db()
    try:
        blocked = list_tasks(conn, status="blocked_approval", limit=50)
        approvals = []
        for task in blocked:
            pending = get_pending_approvals(conn, task["task_id"])
            for a in pending:
                approvals.append({**a, "task_title": task["title"], "task": task})
        return jsonify(approvals)
    finally:
        conn.close()


@app.route("/api/approvals/<approval_id>/decide", methods=["POST"])
def api_decide_approval(approval_id):
    data = request.get_json(force=True) or {}
    approved = bool(data.get("approved", False))
    note = data.get("note", "")
    conn = get_db()
    try:
        result = approve_task(conn, approval_id, approved=approved, decided_by="human", decision_note=note)
        conn.commit()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/memory")
def api_memory():
    conn = get_db()
    try:
        memories = get_memories(conn)
        return jsonify(memories[:50])
    finally:
        conn.close()


@app.route("/api/revenue/daily")
def api_daily_revenue():
    conn = get_db()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        revenue = get_daily_revenue(conn, today)
        return jsonify({"date": today, "revenue": revenue})
    finally:
        conn.close()


@app.route("/api/health")
def api_health():
    conn = get_db()
    try:
        health = run_health_check(conn)
        return jsonify(health_to_dict(health))
    finally:
        conn.close()


@app.route("/api/workstreams")
def api_workstreams():
    conn = get_db()
    try:
        summary = get_workstream_summary()
        # Enrich with live task counts per workstream
        for ws in summary:
            wid = ws["workstream_id"]
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM ceo_tasks WHERE workstream_id=? GROUP BY status",
                (wid,),
            ).fetchall()
            counts = {r["status"]: r["cnt"] for r in rows}
            ws["task_counts"] = counts
            ws["total_tasks"] = sum(counts.values())
        return jsonify(summary)
    finally:
        conn.close()


@app.route("/api/workers")
def api_workers():
    dispatcher = get_dispatcher()
    return jsonify(dispatcher.get_worker_stats())


@app.route("/api/tasks/<task_id>/dispatch", methods=["POST"])
def api_dispatch_task(task_id):
    conn = get_db()
    try:
        task = get_task(conn, task_id)
        if not task:
            abort(404)
        if task["status"] != "assigned":
            return jsonify({"error": f"Task must be 'assigned' to dispatch, got '{task['status']}'"}), 400
        dispatcher = get_dispatcher()
        result = dispatcher.dispatch(conn, task)
        conn.commit()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/tasks/<task_id>/run", methods=["POST"])
def api_run_task(task_id):
    """Convenience: assign + dispatch in one call for tasks that don't need approval."""
    conn = get_db()
    try:
        task = get_task(conn, task_id)
        if not task:
            abort(404)
        if task["status"] == "queued":
            assign_result = assign_task(conn, task_id, policy=POLICY)
            conn.commit()
            if assign_result["status"] == "blocked_approval":
                return jsonify({**assign_result, "task_id": task_id}), 202
            # Re-fetch after status change
            task = get_task(conn, task_id)
        if task["status"] == "assigned":
            dispatcher = get_dispatcher()
            result = dispatcher.dispatch(conn, task)
            conn.commit()
            return jsonify(result)
        return jsonify({"task_id": task_id, "status": task["status"], "message": "no action taken"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()


@app.route("/api/autopilot/cycle", methods=["POST"])
def api_autopilot_cycle():
    """Run one full CEO cycle: brain → assign → dispatch → report."""
    pilot = get_auto_pilot(DB_PATH)
    report = pilot.run_cycle()
    return jsonify(cycle_report_to_dict(report))


@app.route("/api/autopilot/seed", methods=["POST"])
def api_autopilot_seed():
    """Seed all profit pipelines via the CEO Brain."""
    pilot = get_auto_pilot(DB_PATH)
    result = pilot.seed()
    return jsonify(result)


@app.route("/api/autopilot/run", methods=["POST"])
def api_autopilot_run():
    """Run N cycles (default 3). Body: {cycles: int}"""
    data = request.get_json(force=True) or {}
    n = int(data.get("cycles", 3))
    n = min(n, 10)  # cap at 10 per HTTP request
    pilot = get_auto_pilot(DB_PATH)
    reports = pilot.run_continuous(cycles=n, delay_seconds=0.1)
    return jsonify({
        "cycles_run": len(reports),
        "reports": [cycle_report_to_dict(r) for r in reports],
        "summary": {
            "total_tasks_created": sum(r.brain_result.get("tasks_created", 0) for r in reports),
            "total_dispatched": sum(r.tasks_dispatched for r in reports),
            "total_completed": sum(r.tasks_completed for r in reports),
            "total_failed": sum(r.tasks_failed for r in reports),
            "daily_revenue": reports[-1].daily_revenue if reports else 0.0,
        },
    })


@app.route("/api/autopilot/start", methods=["POST"])
def api_autopilot_start():
    global _autopilot_thread, _autopilot_active
    if _autopilot_active:
        return jsonify({"status": "already_running"})
    _autopilot_active = True
    _autopilot_thread = threading.Thread(target=_autopilot_loop, daemon=True, name="ceo-autopilot")
    _autopilot_thread.start()
    log.info("Autopilot started — interval=%ds", _autopilot_interval)
    return jsonify({"status": "started", "interval_seconds": _autopilot_interval})


@app.route("/api/autopilot/stop", methods=["POST"])
def api_autopilot_stop():
    global _autopilot_active
    _autopilot_active = False
    log.info("Autopilot stop requested")
    return jsonify({"status": "stopping"})


@app.route("/api/autopilot/status")
def api_autopilot_status():
    pilot = get_auto_pilot(DB_PATH)
    conn = get_db()
    try:
        from ceo.db import get_total_metrics
        metrics = get_total_metrics(conn)
        secs_since = round(time.time() - _last_cycle_at) if _last_cycle_at else None
        next_in = max(0, _autopilot_interval - secs_since) if secs_since is not None else None
        return jsonify({
            "cycles_run": pilot.cycle_count,
            "is_running": _autopilot_active,
            "daily_revenue": get_daily_revenue(conn),
            "total_revenue": metrics["total_revenue"],
            "task_counts": metrics["task_counts"],
            "interval_seconds": _autopilot_interval,
            "seconds_since_cycle": secs_since,
            "next_cycle_in": next_in,
        })
    finally:
        conn.close()


@app.route("/api/revenue/record", methods=["POST"])
def api_record_revenue():
    """Manually record revenue (for when real money comes in)."""
    data = request.get_json(force=True) or {}
    amount = float(data.get("amount", 0))
    workstream_id = data.get("workstream_id")
    source = data.get("source", "manual")
    if amount <= 0:
        return jsonify({"error": "amount must be positive"}), 400
    conn = get_db()
    try:
        from ceo.db import record_metric
        record_metric(
            conn,
            metric_name="revenue",
            metric_value=amount,
            workstream_id=workstream_id,
            context={"source": source},
        )
        conn.commit()
        return jsonify({"recorded": amount, "workstream_id": workstream_id})
    finally:
        conn.close()


@app.route("/api/intelligence")
def api_intelligence():
    """Workstream scores, tier state, and unlock progress."""
    conn = get_db()
    try:
        scores = load_scores(conn)
        tier   = load_tier_state(conn)
        if not tier:
            from ceo.db import get_daily_revenue as _dr
            tier = persist_tier_state(conn, _dr(conn))
            conn.commit()
        return jsonify({"scores": scores, "tier": tier, "unlock_tiers": UNLOCK_TIERS})
    finally:
        conn.close()


@app.route("/api/assets")
def api_assets():
    """Return completed asset tasks with their preview SVGs and metadata."""
    conn = get_db()
    try:
        import json as _json
        rows = conn.execute(
            """
            SELECT task_id, title, workstream_id, status, result_json, updated_at
            FROM ceo_tasks
            WHERE workstream_id IN ('assets_2d','assets_3d','assets','youtube','gumroad','fiverr','etsy')
              AND status = 'completed'
              AND result_json IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 60
            """,
        ).fetchall()
        assets = []
        for row in rows:
            result = {}
            if row["result_json"]:
                try:
                    result = _json.loads(row["result_json"]) if isinstance(row["result_json"], str) else row["result_json"]
                except Exception:
                    pass
            # Fiverr gig fields
            if row["workstream_id"] == "fiverr":
                gig = result.get("gig", {})
                assets.append({
                    "task_id":       row["task_id"],
                    "title":         row["title"],
                    "workstream_id": row["workstream_id"],
                    "asset_type":    "fiverr_gig",
                    "style":         gig.get("category", ""),
                    "preview_svg":   None,
                    "preview_url":   result.get("preview_url") or gig.get("preview_url"),
                    "formats":       ["Fiverr Gig"],
                    "platforms":     ["fiverr"],
                    "listing_ready": result.get("listing_ready", True),
                    "price_usd":     gig.get("packages", {}).get("basic", {}).get("price", 15),
                    "gig_title":     gig.get("title", ""),
                    "gig_tags":      gig.get("tags", []),
                    "packages":      gig.get("packages", {}),
                    "post_instructions": result.get("post_instructions", ""),
                    "updated_at":    row["updated_at"],
                })
            # YouTube Shorts special fields
            elif row["workstream_id"] == "youtube":
                assets.append({
                    "task_id":      row["task_id"],
                    "title":        row["title"],
                    "workstream_id": row["workstream_id"],
                    "asset_type":   "youtube_short",
                    "style":        result.get("niche", ""),
                    "preview_svg":  None,
                    "preview_url":  f"https://youtu.be/{result['video_id']}" if result.get("video_id") else None,
                    "formats":      ["MP4"],
                    "platforms":    ["youtube"],
                    "listing_ready": result.get("listing_ready", False),
                    "price_usd":    0.0,
                    "video_id":     result.get("video_id"),
                    "upload_status": result.get("upload_status"),
                    "updated_at":   row["updated_at"],
                })
            else:
                assets.append({
                    "task_id":      row["task_id"],
                    "title":        row["title"],
                    "workstream_id": row["workstream_id"],
                    "asset_type":   result.get("asset_type") or result.get("model_type") or "asset",
                    "style":        result.get("style", ""),
                    "preview_svg":  result.get("preview_svg") or result.get("output", {}).get("preview_svg"),
                    "preview_url":  result.get("preview_url"),
                    "formats":      result.get("formats", []),
                    "platforms":    result.get("platforms", []),
                    "listing_ready": result.get("listing_ready", False),
                    "price_usd":    (result.get("economic_data") or {}).get("price_usd", 0),
                    "updated_at":   row["updated_at"],
                })
        return jsonify(assets)
    finally:
        conn.close()


@app.route("/api/listings")
def api_listings():
    """All completed listing/posting tasks with result details and any URLs."""
    conn = get_db()
    try:
        import json as _json
        rows = conn.execute(
            """
            SELECT task_id, title, workstream_id, status, result_json, created_at, updated_at
            FROM ceo_tasks
            WHERE status = 'completed'
              AND result_json IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 100
            """,
        ).fetchall()
        listings = []
        for row in rows:
            result = {}
            if row["result_json"]:
                try:
                    result = _json.loads(row["result_json"]) if isinstance(row["result_json"], str) else row["result_json"]
                except Exception:
                    pass
            url = (
                result.get("url")
                or result.get("listing_url")
                or result.get("gig_url")
                or result.get("product_url")
                or result.get("preview_url")
            )
            if result.get("video_id"):
                url = f"https://youtu.be/{result['video_id']}"
            listings.append({
                "task_id":       row["task_id"],
                "title":         row["title"],
                "workstream_id": row["workstream_id"],
                "updated_at":    row["updated_at"],
                "url":           url,
                "price":         (result.get("economic_data") or {}).get("price_usd")
                                  or result.get("price_usd")
                                  or (result.get("gig") or {}).get("packages", {}).get("basic", {}).get("price"),
                "platform":      result.get("platform") or row["workstream_id"],
                "listing_ready": result.get("listing_ready", False),
                "preview_url":   result.get("preview_url"),
                "summary":       result.get("post_instructions") or result.get("description") or "",
            })
        return jsonify(listings)
    finally:
        conn.close()


@app.route("/api/flush-old-tasks", methods=["POST"])
def api_flush_old_tasks():
    """Delete all stale/fake tasks and reset revenue counters."""
    conn = get_db()
    try:
        # Count before
        before = conn.execute("SELECT COUNT(*) FROM ceo_tasks").fetchone()[0]

        # Delete everything that isn't a real Gumroad post
        # Real = completed AND result_json contains a gumroad.com URL
        conn.execute("""
            DELETE FROM ceo_tasks
            WHERE NOT (
                status = 'completed'
                AND result_json LIKE '%gumroad.com%'
            )
        """)

        after = conn.execute("SELECT COUNT(*) FROM ceo_tasks").fetchone()[0]

        # Reset revenue counters in ceo_state if that table exists
        try:
            conn.execute("UPDATE ceo_state SET value='0' WHERE key IN ('total_revenue','today_revenue')")
        except Exception:
            pass

        conn.commit()

        return jsonify({
            "ok": True,
            "deleted": before - after,
            "remaining_real_listings": after,
            "message": "Flushed. Only real Gumroad listings kept.",
        })
    except Exception as e:
        log.error("flush-old-tasks error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/stores")
def api_stores():
    """Return active store status across all platforms."""
    conn = get_db()
    try:
        import json as _json
        platforms = ["gumroad", "itch.io", "fiverr", "cgtrader", "turbosquid", "creative_market", "etsy", "youtube"]
        stores = []
        for platform in platforms:
            search_key = platform.split("_")[0].replace(".", "")
            rows = conn.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed
                FROM ceo_tasks
                WHERE (workstream_id=? OR workstream_id LIKE ?)
                   OR (result_json LIKE ? OR title LIKE ?)
                """,
                (search_key, f"{search_key}%", f'%"{platform}"%', f"%{platform}%"),
            ).fetchone()
            stores.append({
                "platform": platform,
                "label":    platform.replace("_", " ").replace(".", " ").title(),
                "listings": rows["completed"] or 0,
                "active":   (rows["completed"] or 0) > 0,
                "free":     platform in ("gumroad", "itch.io", "youtube"),
            })
        return jsonify(stores)
    finally:
        conn.close()


@app.route("/api/fiverr/post", methods=["POST"])
def api_fiverr_post():
    """Launch Playwright to auto-fill a Fiverr gig form. Human clicks Publish."""
    data = request.get_json(force=True) or {}
    task_id = data.get("task_id")
    conn = get_db()
    try:
        import json as _json
        gig_data = {}
        if task_id:
            task = get_task(conn, task_id)
            if task and task.get("result_json"):
                result = _json.loads(task["result_json"]) if isinstance(task["result_json"], str) else task["result_json"]
                gig_data = result.get("gig", {})
        if not gig_data:
            gig_data = data.get("gig", {})
        if not gig_data:
            return jsonify({"error": "No gig data provided"}), 400
        from ceo.workers.fiverr_post import post_gig_to_fiverr
        result = post_gig_to_fiverr(gig_data, headless=False)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ── UI Routes ──────────────────────────────────────────────────────────────


@app.route("/")
def dashboard():
    return render_template("index.html")


if os.environ.get("CEO_AUTOSTART", "").lower() == "true":
    _autopilot_active = True
    _autopilot_thread = threading.Thread(target=_autopilot_loop, daemon=True, name="ceo-autopilot")
    _autopilot_thread.start()
    log.info("CEO_AUTOSTART: autopilot launched on boot — interval=%ds", _autopilot_interval)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "false").lower() == "true")

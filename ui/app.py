"""
CEO GIR Dashboard — Flask web UI.
Game-like control panel to visualize and operate the agent ecosystem.
"""
import os
import json
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, abort
from flask_cors import CORS

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


@app.route("/api/autopilot/status")
def api_autopilot_status():
    pilot = get_auto_pilot(DB_PATH)
    conn = get_db()
    try:
        from ceo.db import get_total_metrics
        metrics = get_total_metrics(conn)
        return jsonify({
            "cycles_run": pilot.cycle_count,
            "is_running": pilot._running,
            "daily_revenue": get_daily_revenue(conn),
            "total_revenue": metrics["total_revenue"],
            "task_counts": metrics["task_counts"],
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
            WHERE workstream_id IN ('assets_2d','assets_3d','assets')
              AND status = 'completed'
              AND result_json IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 40
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
            assets.append({
                "task_id":      row["task_id"],
                "title":        row["title"],
                "workstream_id": row["workstream_id"],
                "asset_type":   result.get("asset_type") or result.get("model_type") or "asset",
                "style":        result.get("style", ""),
                "preview_svg":  result.get("preview_svg") or result.get("output", {}).get("preview_svg"),
                "formats":      result.get("formats", []),
                "platforms":    result.get("platforms", []),
                "listing_ready": result.get("listing_ready", False),
                "price_usd":    (result.get("economic_data") or {}).get("price_usd", 0),
                "updated_at":   row["updated_at"],
            })
        return jsonify(assets)
    finally:
        conn.close()


@app.route("/api/stores")
def api_stores():
    """Return active store status across all platforms."""
    conn = get_db()
    try:
        import json as _json
        platforms = ["etsy", "fiverr", "cgtrader", "turbosquid", "creative_market", "gumroad"]
        stores = []
        for platform in platforms:
            rows = conn.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed
                FROM ceo_tasks
                WHERE (workstream_id=? OR result_json LIKE ?)
                  AND (title LIKE ? OR result_json LIKE ?)
                """,
                (platform.split("_")[0], f'%"{platform}"%', f"%{platform}%", f'%"{platform}"%'),
            ).fetchone()
            stores.append({
                "platform": platform,
                "label":    platform.replace("_", " ").title(),
                "listings": rows["completed"] or 0,
                "active":   (rows["completed"] or 0) > 0,
            })
        return jsonify(stores)
    finally:
        conn.close()


# ── UI Routes ──────────────────────────────────────────────────────────────


@app.route("/")
def dashboard():
    return render_template("index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "false").lower() == "true")

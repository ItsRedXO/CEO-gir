"""
CEO GIR — entry point.

Run the dashboard:
    python main.py

Run tests:
    PYTHONPATH="$PWD" pytest -q tests/test_ceo_economics_integration.py
    PYTHONPATH="$PWD" pytest -q
"""
import os
import sys

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "ui"

    if mode == "ui":
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        from ui.app import app
        port = int(os.environ.get("PORT", 5000))
        print(f"CEO GIR dashboard → http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=True)

    elif mode == "seed":
        from ceo.db import init_db, get_total_metrics
        from ceo.orchestration import create_and_queue_task
        conn = init_db()
        seed_tasks = [
            {"title": "Research Etsy digital products opportunity", "workstream_id": "research", "required_capabilities": ["research"]},
            {"title": "Research Fiverr gig market demand", "workstream_id": "research", "required_capabilities": ["research"]},
            {"title": "Create affiliate content piece", "workstream_id": "content", "required_capabilities": ["content", "writing"]},
            {"title": "Analyze YouTube monetization path", "workstream_id": "research", "required_capabilities": ["research", "analysis"]},
        ]
        for t in seed_tasks:
            tid = create_and_queue_task(conn, **t, created_by="seed")
            print(f"  Created: {tid[:8]}... — {t['title']}")
        conn.commit()
        conn.close()
        print("Seed complete.")

    elif mode == "status":
        from ceo.db import init_db, get_total_metrics, get_daily_revenue
        from ceo.replanning import get_ceo_decision_context
        conn = init_db()
        metrics = get_total_metrics(conn)
        daily = get_daily_revenue(conn)
        ctx = get_ceo_decision_context(conn)
        conn.close()
        print(f"Daily revenue:    ${daily:.2f}")
        print(f"Total revenue:    ${metrics['total_revenue']:.2f}")
        print(f"Total profit:     ${metrics['total_profit']:.2f}")
        print(f"Queued tasks:     {ctx['queued_count']}")
        print(f"In progress:      {ctx['in_progress_count']}")
        print(f"Blocked:          {ctx['blocked_count']}")
        print(f"Task counts:      {metrics['task_counts']}")

    elif mode == "autopilot":
        from ceo.db import init_db
        from ceo.agents.auto_pilot import get_auto_pilot, cycle_report_to_dict
        import json

        cycles = int(os.environ.get("CEO_CYCLES", "20"))
        delay  = float(os.environ.get("CEO_CYCLE_DELAY", "1.0"))
        db_path = os.environ.get("CEO_GIR_DB", "ceo_gir.db")

        conn = init_db(db_path)
        conn.close()

        pilot = get_auto_pilot(db_path)
        print(f"CEO GIR autopilot starting — {cycles} cycles, {delay}s between each")
        print("Seeding profit pipelines…")
        seed_result = pilot.seed()
        print(f"  Seeded {seed_result['seeded']} tasks across all workstreams")

        def on_cycle(report):
            br = report.brain_result
            print(
                f"  Cycle {report.cycle_number:3d} | "
                f"created={br.get('tasks_created', 0):3d} "
                f"dispatched={report.tasks_dispatched:3d} "
                f"completed={report.tasks_completed:3d} "
                f"failed={report.tasks_failed:2d} | "
                f"daily=${report.daily_revenue:.2f}"
                + (f" | ERRORS: {report.errors}" if report.errors else "")
            )

        pilot.run_continuous(cycles=cycles, delay_seconds=delay, on_cycle=on_cycle)
        print("Autopilot complete.")

    elif mode == "brain":
        from ceo.db import init_db
        from ceo.agents.ceo_brain import get_brain
        import json

        db_path = os.environ.get("CEO_GIR_DB", "ceo_gir.db")
        conn = init_db(db_path)
        result = get_brain().run_cycle(conn)
        conn.close()
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python main.py [ui|seed|status|autopilot|brain]")
        sys.exit(1)


if __name__ == "__main__":
    main()

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

    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python main.py [ui|seed|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()

import sqlite3
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

CEO_SCHEMA_VERSION = 4
DEFAULT_DB_PATH = "ceo_gir.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ceo_tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    workstream_id TEXT,
    agent_id TEXT,
    opportunity_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 5,
    side_effect_type TEXT,
    input_json TEXT,
    result_json TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    parent_task_id TEXT,
    required_capabilities TEXT
);

CREATE TABLE IF NOT EXISTS ceo_approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_by TEXT,
    requested_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    FOREIGN KEY (task_id) REFERENCES ceo_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS ceo_task_results (
    result_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    output_json TEXT,
    error TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES ceo_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS ceo_metric_observations (
    obs_id TEXT PRIMARY KEY,
    task_id TEXT,
    workstream_id TEXT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    observed_at TEXT NOT NULL,
    context_json TEXT
);

CREATE TABLE IF NOT EXISTS ceo_opportunity_outcomes (
    outcome_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    task_id TEXT,
    revenue REAL NOT NULL DEFAULT 0.0,
    spend REAL NOT NULL DEFAULT 0.0,
    fees REAL NOT NULL DEFAULT 0.0,
    profit REAL NOT NULL DEFAULT 0.0,
    roi REAL,
    roas REAL,
    currency TEXT NOT NULL DEFAULT 'USD',
    recorded_at TEXT NOT NULL,
    context_json TEXT
);

CREATE TABLE IF NOT EXISTS ceo_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ceo_memory (
    memory_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    context_json TEXT
);
"""


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)

    version = conn.execute("SELECT version FROM schema_version").fetchone()
    if version is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (CEO_SCHEMA_VERSION,))
    conn.commit()
    return conn


@contextmanager
def get_conn(db_path: str = DEFAULT_DB_PATH):
    conn = init_db(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_task(
    conn: sqlite3.Connection,
    title: str,
    description: str = "",
    workstream_id: str = None,
    agent_id: str = None,
    opportunity_id: str = None,
    priority: int = 5,
    side_effect_type: str = None,
    input_data: dict = None,
    created_by: str = "ceo",
    max_retries: int = 3,
    parent_task_id: str = None,
    required_capabilities: list = None,
) -> str:
    task_id = _new_id()
    now = _now()
    conn.execute(
        """
        INSERT INTO ceo_tasks
          (task_id, title, description, workstream_id, agent_id, opportunity_id,
           status, priority, side_effect_type, input_json, created_by,
           created_at, updated_at, retry_count, max_retries, parent_task_id,
           required_capabilities)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, title, description, workstream_id, agent_id, opportunity_id,
            "queued", priority, side_effect_type,
            json.dumps(input_data or {}), created_by,
            now, now, 0, max_retries, parent_task_id,
            json.dumps(required_capabilities or []),
        ),
    )
    return task_id


def get_task(conn: sqlite3.Connection, task_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM ceo_tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return _task_row_to_dict(row)


def _task_row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("input_json", "result_json", "required_capabilities"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def update_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    status: str,
    result_json: dict = None,
) -> None:
    now = _now()
    if result_json is not None:
        conn.execute(
            "UPDATE ceo_tasks SET status=?, result_json=?, updated_at=? WHERE task_id=?",
            (status, json.dumps(result_json), now, task_id),
        )
    else:
        conn.execute(
            "UPDATE ceo_tasks SET status=?, updated_at=? WHERE task_id=?",
            (status, now, task_id),
        )


def create_approval(
    conn: sqlite3.Connection,
    task_id: str,
    action_type: str,
    requested_by: str = "ceo",
) -> str:
    approval_id = _new_id()
    conn.execute(
        """
        INSERT INTO ceo_approvals
          (approval_id, task_id, action_type, status, requested_by, requested_at)
        VALUES (?,?,?,?,?,?)
        """,
        (approval_id, task_id, action_type, "pending", requested_by, _now()),
    )
    return approval_id


def get_pending_approvals(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM ceo_approvals WHERE task_id=? AND status='pending'",
        (task_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def decide_approval(
    conn: sqlite3.Connection,
    approval_id: str,
    approved: bool,
    decided_by: str = "human",
    decision_note: str = "",
) -> None:
    status = "approved" if approved else "rejected"
    conn.execute(
        """
        UPDATE ceo_approvals
        SET status=?, decided_by=?, decided_at=?, decision_note=?
        WHERE approval_id=?
        """,
        (status, decided_by, _now(), decision_note, approval_id),
    )


def has_approved_record(conn: sqlite3.Connection, task_id: str, action_type: str = None) -> bool:
    if action_type:
        row = conn.execute(
            "SELECT 1 FROM ceo_approvals WHERE task_id=? AND action_type=? AND status='approved'",
            (task_id, action_type),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM ceo_approvals WHERE task_id=? AND status='approved'",
            (task_id,),
        ).fetchone()
    return row is not None


def has_any_pending_approval(conn: sqlite3.Connection, task_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ceo_approvals WHERE task_id=? AND status='pending'",
        (task_id,),
    ).fetchone()
    return row is not None


def record_task_result(
    conn: sqlite3.Connection,
    task_id: str,
    status: str,
    output: dict = None,
    error: str = None,
    duration_ms: int = None,
) -> str:
    result_id = _new_id()
    conn.execute(
        """
        INSERT INTO ceo_task_results
          (result_id, task_id, status, output_json, error, duration_ms, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (result_id, task_id, status, json.dumps(output or {}), error, duration_ms, _now()),
    )
    return result_id


def record_metric(
    conn: sqlite3.Connection,
    metric_name: str,
    metric_value: float,
    task_id: str = None,
    workstream_id: str = None,
    context: dict = None,
) -> str:
    obs_id = _new_id()
    conn.execute(
        """
        INSERT INTO ceo_metric_observations
          (obs_id, task_id, workstream_id, metric_name, metric_value, observed_at, context_json)
        VALUES (?,?,?,?,?,?,?)
        """,
        (obs_id, task_id, workstream_id, metric_name, metric_value, _now(), json.dumps(context or {})),
    )
    return obs_id


def record_opportunity_outcome(
    conn: sqlite3.Connection,
    opportunity_id: str,
    revenue: float,
    spend: float,
    fees: float,
    profit: float,
    roi: float = None,
    roas: float = None,
    currency: str = "USD",
    task_id: str = None,
    context: dict = None,
) -> str:
    outcome_id = _new_id()
    conn.execute(
        """
        INSERT INTO ceo_opportunity_outcomes
          (outcome_id, opportunity_id, task_id, revenue, spend, fees, profit,
           roi, roas, currency, recorded_at, context_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            outcome_id, opportunity_id, task_id, revenue, spend, fees, profit,
            roi, roas, currency, _now(), json.dumps(context or {}),
        ),
    )
    return outcome_id


def set_state(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ceo_state (key, value_json, updated_at) VALUES (?,?,?)",
        (key, json.dumps(value), _now()),
    )


def get_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value_json FROM ceo_state WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row[0])


def add_memory(
    conn: sqlite3.Connection,
    category: str,
    content: str,
    confidence: float = 1.0,
    context: dict = None,
) -> str:
    memory_id = _new_id()
    now = _now()
    conn.execute(
        """
        INSERT INTO ceo_memory
          (memory_id, category, content, confidence, created_at, updated_at, context_json)
        VALUES (?,?,?,?,?,?,?)
        """,
        (memory_id, category, content, confidence, now, now, json.dumps(context or {})),
    )
    return memory_id


def get_memories(conn: sqlite3.Connection, category: str = None) -> list[dict]:
    if category:
        rows = conn.execute(
            "SELECT * FROM ceo_memory WHERE category=? ORDER BY created_at DESC",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ceo_memory ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_tasks(
    conn: sqlite3.Connection,
    status: str = None,
    workstream_id: str = None,
    limit: int = 100,
) -> list[dict]:
    parts = []
    params = []
    if status:
        parts.append("status=?")
        params.append(status)
    if workstream_id:
        parts.append("workstream_id=?")
        params.append(workstream_id)
    where = "WHERE " + " AND ".join(parts) if parts else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM ceo_tasks {where} ORDER BY priority ASC, created_at ASC LIMIT ?",
        params,
    ).fetchall()
    return [_task_row_to_dict(r) for r in rows]


def get_daily_revenue(conn: sqlite3.Connection, date_str: str = None) -> float:
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT SUM(revenue) FROM ceo_opportunity_outcomes WHERE recorded_at LIKE ?",
        (f"{date_str}%",),
    ).fetchone()
    return row[0] or 0.0


def get_total_metrics(conn: sqlite3.Connection) -> dict:
    revenue_row = conn.execute("SELECT SUM(revenue), SUM(spend), SUM(fees), SUM(profit) FROM ceo_opportunity_outcomes").fetchone()
    task_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM ceo_tasks GROUP BY status"
    ).fetchall()
    task_counts = {r["status"]: r["cnt"] for r in task_rows}
    return {
        "total_revenue": revenue_row[0] or 0.0,
        "total_spend": revenue_row[1] or 0.0,
        "total_fees": revenue_row[2] or 0.0,
        "total_profit": revenue_row[3] or 0.0,
        "task_counts": task_counts,
    }

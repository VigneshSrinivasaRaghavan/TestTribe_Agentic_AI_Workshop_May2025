from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

DB_PATH = Path("outputs/memory/ui_memory.db")

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")  # safer concurrent writes
    return conn

def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            total INT,
            passed INT,
            failed INT,
            skipped INT,
            llm_summary TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INT,
            name TEXT,
            suite TEXT,
            status TEXT,
            message TEXT,
            details TEXT,
            attempt INT,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
        """
    )

    conn.commit()
    conn.close()


def save_run(
    project: str,
    summary: Dict[str, Any],
    results: List[Dict[str, Any]],
    llm_summary: str = "",
) -> None:
    """Persist run summary + results into DB."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO runs (project, total, passed, failed, skipped, llm_summary)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            project,
            int(summary.get("total", 0)),
            int(summary.get("passed", 0)),
            int(summary.get("failed", 0)),
            int(summary.get("skipped", 0)),
            llm_summary,
        ),
    )
    run_id = cur.lastrowid

    for case in results:
        cur.execute(
            """
            INSERT INTO results (run_id, name, suite, status, message, details, attempt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                case.get("name", ""),
                case.get("suite", ""),
                case.get("status", ""),
                case.get("message", ""),
                case.get("details", ""),
                int(case.get("attempt", 1)),
            ),
        )

    conn.commit()
    conn.close()

def find_recurrences(name: str, message: str, days: Optional[int] = None) -> int:
    """Return how many times this test failure was seen before.
       If days is given, only count within that many past days.
    """
    conn = _get_conn()
    cur = conn.cursor()

    if days is not None:
        cur.execute(
            """
            SELECT COUNT(*) FROM results r
            JOIN runs u ON r.run_id = u.id
            WHERE r.name = ? AND r.status = 'failed' AND r.message = ?
              AND u.ts >= datetime('now', ?)
            """,
            (name, message, f'-{days} days'),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) FROM results
            WHERE name = ? AND status = 'failed' AND message = ?
            """,
            (name, message),
        )

    count = cur.fetchone()[0]
    conn.close()
    return int(count)


# Run once on import to ensure schema exists
init_db()
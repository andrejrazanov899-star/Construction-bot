"""
База данных SQLite
Таблицы: users, objects, reports, issues, workers
"""

import sqlite3
from datetime import date, timedelta
from typing import Optional


class Database:
    def __init__(self, path: str = "construction.db"):
        self.path = path

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                full_name   TEXT,
                username    TEXT,
                created_at  TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS objects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                status      TEXT DEFAULT 'active',
                created_by  INTEGER,
                created_at  TEXT DEFAULT (date('now')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                obj_id        INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                report_date   TEXT NOT NULL,
                workers_count INTEGER NOT NULL,
                volume        REAL NOT NULL,
                unit          TEXT NOT NULL,
                notes         TEXT DEFAULT '',
                created_at    TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (obj_id)  REFERENCES objects(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS issues (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                obj_id      INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                text        TEXT NOT NULL,
                priority    TEXT DEFAULT 'medium',
                status      TEXT DEFAULT 'open',
                created_at  TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                FOREIGN KEY (obj_id)  REFERENCES objects(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS workers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                role       TEXT NOT NULL,
                active     INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (date('now'))
            );
            """)

    def ensure_user(self, user_id: int, full_name: str, username: Optional[str]):
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO users (id, full_name, username) VALUES (?,?,?)",
                (user_id, full_name, username),
            )
            c.execute(
                "UPDATE users SET full_name=?, username=? WHERE id=?",
                (full_name, username, user_id),
            )

    def add_object(self, name: str, description: str, created_by: int) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO objects (name, description, created_by) VALUES (?,?,?)",
                (name, description, created_by),
            )
            return cur.lastrowid

    def get_objects(self, status: Optional[str] = None):
        with self._conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM objects WHERE status=? ORDER BY id", (status,)
                ).fetchall()
            else:
                rows = c.execute("SELECT * FROM objects ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_object(self, obj_id: int):
        with self._conn() as c:
            row = c.execute("SELECT * FROM objects WHERE id=?", (obj_id,)).fetchone()
            return dict(row) if row else None

    def set_object_status(self, obj_id: int, status: str):
        with self._conn() as c:
            c.execute("UPDATE objects SET status=? WHERE id=?", (status, obj_id))

    def add_report(self, obj_id, user_id, report_date, workers_count, volume, unit, notes) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO reports
                   (obj_id, user_id, report_date, workers_count, volume, unit, notes)
                   VALUES (?,?,?,?,?,?,?)""",
                (obj_id, user_id, report_date, workers_count, volume, unit, notes),
            )
            return cur.lastrowid

    def get_reports(self, obj_id: int, limit: int = 10):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM reports WHERE obj_id=? ORDER BY report_date DESC LIMIT ?",
                (obj_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_reports_for_date(self, obj_id: int, report_date: str):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM reports WHERE obj_id=? AND report_date=?",
                (obj_id, report_date),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_reports(self, limit: int = 10):
        with self._conn() as c:
            rows = c.execute(
                """SELECT r.*, o.name AS obj_name
                   FROM reports r
                   JOIN objects o ON o.id = r.obj_id
                   ORDER BY r.report_date DESC, r.id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def add_issue(self, obj_id: int, user_id: int, text: str, priority: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO issues (obj_id, user_id, text, priority) VALUES (?,?,?,?)",
                (obj_id, user_id, text, priority),
            )
            return cur.lastrowid

    def get_open_issues(self):
        with self._conn() as c:
            rows = c.execute(
                """SELECT i.*, o.name AS obj_name
                   FROM issues i JOIN objects o ON o.id = i.obj_id
                   WHERE i.status='open'
                   ORDER BY CASE i.priority
                       WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                       WHEN 'medium' THEN 3 ELSE 4 END""",
            ).fetchall()
            return [dict(r) for r in rows]

    def resolve_issue(self, issue_id: int):
        with self._conn() as c:
            c.execute(
                "UPDATE issues SET status='resolved', resolved_at=datetime('now') WHERE id=?",
                (issue_id,),
            )

    def add_worker(self, name: str, role: str) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO workers (name, role) VALUES (?,?)", (name, role))
            return cur.lastrowid

    def get_workers(self, active_only: bool = True):
        with self._conn() as c:
            if active_only:
                rows = c.execute(
                    "SELECT * FROM workers WHERE active=1 ORDER BY name"
                ).fetchall()
            else:
                rows = c.execute("SELECT * FROM workers ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        week_ago = str(date.today() - timedelta(days=7))
        with self._conn() as c:
            total_obj   = c.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
            rep_week    = c.execute(
                "SELECT COUNT(*) FROM reports WHERE report_date >= ?", (week_ago,)
            ).fetchone()[0]
            open_issues = c.execute(
                "SELECT COUNT(*) FROM issues WHERE status='open'"
            ).fetchone()[0]
            tot_workers = c.execute(
                "SELECT COUNT(*) FROM workers WHERE active=1"
            ).fetchone()[0]
        return {
            "total_objects": total_obj,
            "reports_week":  rep_week,
            "open_issues":   open_issues,
            "total_workers": tot_workers,
        }

    def get_object_stats(self, obj_id: int) -> dict:
        week_ago = str(date.today() - timedelta(days=7))
        with self._conn() as c:
            rows = c.execute(
                """SELECT workers_count, volume, unit FROM reports
                   WHERE obj_id=? AND report_date >= ?""",
                (obj_id, week_ago),
            ).fetchall()
        if not rows:
            return {"reports": 0, "avg_workers": 0, "total_volume": 0, "unit": ""}
        rows = [dict(r) for r in rows]
        n = len(rows)
        avg_w   = sum(r["workers_count"] for r in rows) / n
        total_v = sum(r["volume"] for r in rows)
        unit    = rows[-1]["unit"] if rows else ""
        return {"reports": n, "avg_workers": avg_w, "total_volume": total_v, "unit": unit}
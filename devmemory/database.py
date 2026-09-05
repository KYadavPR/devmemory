"""DevMemory SQLite database layer."""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional


class DevMemoryDB:
    """SQLite storage for DevMemory project metadata."""

    def __init__(self, project_path: str):
        db_path = os.path.join(project_path, ".devmemory", "devmemory.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def initialize(self):
        """Create all tables."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS project (
                project_id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                current_version INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS versions (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                checkpoint_id TEXT,
                session_id TEXT,
                agent TEXT,
                intent TEXT,
                git_commit TEXT NOT NULL,
                parent_commit TEXT,
                branch TEXT,
                changed_files TEXT,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                feature TEXT,
                status TEXT DEFAULT 'NEEDS_REVIEW',
                tests_passed INTEGER,
                tests_failed INTEGER,
                metrics TEXT,
                errors TEXT,
                analysis TEXT,
                recommendation TEXT,
                is_regression INTEGER DEFAULT 0,
                artifact_path TEXT,
                FOREIGN KEY (project_id) REFERENCES project(project_id)
            );

            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'NOT_STARTED',
                latest_metrics TEXT,
                UNIQUE(project_id, name)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                version_id INTEGER,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT DEFAULT 'devmemory',
                data TEXT
            );
        """
        )
        # FTS5 for full-text search
        try:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS versions_fts USING fts5(
                    intent, agent, feature, analysis, recommendation, changed_files,
                    content='versions',
                    content_rowid='version_id'
                );
            """
            )
        except sqlite3.OperationalError:
            pass  # FTS5 may not be available on all SQLite builds
        self.conn.commit()

    # ── Project CRUD ──────────────────────────────────────────────

    def create_project(self, project_id: str, project_name: str, root_path: str):
        self.conn.execute(
            """INSERT OR REPLACE INTO project (project_id, project_name, root_path, created_at, current_version)
               VALUES (?, ?, ?, ?, 0)""",
            (project_id, project_name, root_path, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_project(self) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM project LIMIT 1").fetchone()
        return dict(row) if row else None

    def update_current_version(self, version_id: int):
        self.conn.execute(
            "UPDATE project SET current_version = ?", (version_id,)
        )
        self.conn.commit()

    # ── Version CRUD ──────────────────────────────────────────────

    def create_version(self, **kwargs) -> int:
        """Create a new development version. Returns the new version_id."""
        # Serialize complex fields to JSON
        if "changed_files" in kwargs and isinstance(kwargs["changed_files"], list):
            kwargs["changed_files"] = json.dumps(kwargs["changed_files"])
        if "metrics" in kwargs and isinstance(kwargs["metrics"], dict):
            kwargs["metrics"] = json.dumps(kwargs["metrics"])
        if "errors" in kwargs and isinstance(kwargs["errors"], list):
            kwargs["errors"] = json.dumps(kwargs["errors"])

        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        values = list(kwargs.values())

        cursor = self.conn.execute(
            f"INSERT INTO versions ({columns}) VALUES ({placeholders})", values
        )
        version_id = cursor.lastrowid
        self.conn.commit()

        # Update FTS index
        try:
            self.conn.execute(
                """INSERT INTO versions_fts(rowid, intent, agent, feature, analysis, recommendation, changed_files)
                   SELECT version_id, intent, agent, feature, analysis, recommendation, changed_files
                   FROM versions WHERE version_id = ?""",
                (version_id,),
            )
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

        return version_id

    def get_version(self, version_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM versions WHERE version_id = ?", (version_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_versions(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM versions ORDER BY version_id ASC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_version(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM versions ORDER BY version_id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_versions_by_feature(self, feature: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM versions WHERE feature = ? ORDER BY version_id ASC",
            (feature,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_versions(self, query: str) -> list[dict]:
        """Full-text search across version metadata."""
        try:
            rows = self.conn.execute(
                """SELECT v.* FROM versions v
                   JOIN versions_fts fts ON v.version_id = fts.rowid
                   WHERE versions_fts MATCH ?
                   ORDER BY rank""",
                (query,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # Fallback to LIKE search if FTS not available
            like_query = f"%{query}%"
            rows = self.conn.execute(
                """SELECT * FROM versions
                   WHERE intent LIKE ? OR agent LIKE ? OR feature LIKE ?
                   OR analysis LIKE ? OR changed_files LIKE ?
                   ORDER BY version_id DESC""",
                (like_query, like_query, like_query, like_query, like_query),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Feature CRUD ──────────────────────────────────────────────

    def upsert_feature(self, project_id: str, name: str, status: str, metrics: dict = None):
        metrics_json = json.dumps(metrics) if metrics else None
        self.conn.execute(
            """INSERT INTO features (project_id, name, status, latest_metrics)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(project_id, name) DO UPDATE SET
               status = excluded.status,
               latest_metrics = COALESCE(excluded.latest_metrics, features.latest_metrics)""",
            (project_id, name, status, metrics_json),
        )
        self.conn.commit()

    def get_all_features(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM features ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_feature(self, name: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM features WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    # ── Events ────────────────────────────────────────────────────

    def log_event(self, project_id: str, event_type: str, data: dict = None,
                  version_id: int = None, source: str = "devmemory"):
        self.conn.execute(
            """INSERT INTO events (project_id, version_id, event_type, timestamp, source, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, version_id, event_type, datetime.now().isoformat(),
             source, json.dumps(data) if data else None),
        )
        self.conn.commit()

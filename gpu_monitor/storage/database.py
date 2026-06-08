from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


REDUNDANT_INDEXES = (
    "idx_samples_date",
    "idx_gpu_snapshot_date",
    "idx_samples_user_gpu_time",
)


class Database:
    def __init__(self, sqlite_path: str | Path):
        self.sqlite_path = Path(sqlite_path)

    def initialize(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path = Path(__file__).with_name("schema.sql")
        with self.connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            self._run_lightweight_migrations(conn)

    def connect(self) -> sqlite3.Connection:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def storage_stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
            auto_vacuum = int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])

        database_bytes = _file_size(self.sqlite_path)
        wal_bytes = _file_size(Path(str(self.sqlite_path) + "-wal"))
        shm_bytes = _file_size(Path(str(self.sqlite_path) + "-shm"))
        total_bytes = database_bytes + wal_bytes + shm_bytes
        freelist_ratio = freelist_count / page_count if page_count else 0.0

        return {
            "database_bytes": database_bytes,
            "wal_bytes": wal_bytes,
            "shm_bytes": shm_bytes,
            "total_bytes": total_bytes,
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist_count,
            "freelist_ratio": round(freelist_ratio, 4),
            "journal_mode": journal_mode,
            "auto_vacuum": auto_vacuum,
        }

    def compact(self) -> dict[str, Any]:
        before = self.storage_stats()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path, timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            conn.execute("VACUUM")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        finally:
            conn.close()
        return {"before": before, "after": self.storage_stats()}

    @staticmethod
    def _run_lightweight_migrations(conn: sqlite3.Connection) -> None:
        for index_name in REDUNDANT_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0

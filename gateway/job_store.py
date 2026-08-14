from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class JobStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    prompt_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    output_file TEXT,
                    error TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    input_files TEXT NOT NULL DEFAULT '[]',
                    idempotency_key TEXT,
                    created_at REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT 0
                )
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            migrations = {
                "status": "ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'",
                "input_files": "ALTER TABLE jobs ADD COLUMN input_files TEXT NOT NULL DEFAULT '[]'",
                "idempotency_key": "ALTER TABLE jobs ADD COLUMN idempotency_key TEXT",
                "created_at": "ALTER TABLE jobs ADD COLUMN created_at REAL NOT NULL DEFAULT 0",
                "updated_at": "ALTER TABLE jobs ADD COLUMN updated_at REAL NOT NULL DEFAULT 0",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    db.execute(statement)
            now = time.time()
            db.execute("UPDATE jobs SET created_at = ? WHERE created_at = 0", (now,))
            db.execute("UPDATE jobs SET updated_at = created_at WHERE updated_at = 0")
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotency_key "
                "ON jobs(idempotency_key) WHERE idempotency_key IS NOT NULL"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def put(
        self,
        job_id: str,
        prompt_id: str,
        payload: dict[str, Any],
        *,
        input_files: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO jobs(
                    id, prompt_id, payload, status, input_files, idempotency_key,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    prompt_id,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(input_files or [], ensure_ascii=False),
                    idempotency_key,
                    now,
                    now,
                ),
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT prompt_id, payload, output_file, error, status, input_files,
                       idempotency_key, created_at, updated_at
                FROM jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": job_id,
            "prompt_id": row[0],
            "payload": json.loads(row[1]),
            "output_file": row[2],
            "error": row[3],
            "status": row[4],
            "input_files": json.loads(row[5] or "[]"),
            "idempotency_key": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT id FROM jobs WHERE idempotency_key = ?", (key,)).fetchone()
        return self.get(row[0]) if row else None

    def set_output(self, job_id: str, output_file: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE jobs
                SET output_file = ?, status = 'completed', error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (output_file, time.time(), job_id),
            )

    def set_status(self, job_id: str, status: str, error: str | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, time.time(), job_id),
            )

    def clear_input_files(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET input_files = '[]', updated_at = ? WHERE id = ?",
                (time.time(), job_id),
            )

    def expired(self, cutoff: float) -> list[dict[str, Any]]:
        with self._connect() as db:
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM jobs WHERE updated_at < ? AND status IN ('completed', 'failed', 'cancelled')",
                    (cutoff,),
                )
            ]
        return [job for job_id in ids if (job := self.get(job_id))]

    def delete(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

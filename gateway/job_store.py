from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


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
                    error TEXT
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def put(self, job_id: str, prompt_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO jobs(id, prompt_id, payload) VALUES (?, ?, ?)",
                (job_id, prompt_id, json.dumps(payload, ensure_ascii=False)),
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT prompt_id, payload, output_file, error FROM jobs WHERE id = ?",
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
        }

    def set_output(self, job_id: str, output_file: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET output_file = ? WHERE id = ?", (output_file, job_id)
            )


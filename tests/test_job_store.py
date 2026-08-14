import tempfile
import time
import unittest
from pathlib import Path

from gateway.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.temp_dir.name) / "jobs.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_status_files_and_idempotency_are_persisted(self):
        self.store.put(
            "job-1", "prompt-1", {"duration": 15},
            input_files=["input.png"], idempotency_key="storyboard:1",
        )
        job = self.store.get_by_idempotency_key("storyboard:1")
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["input_files"], ["input.png"])
        self.store.set_status("job-1", "failed", "out of memory")
        self.assertEqual(self.store.get("job-1")["error"], "out of memory")

    def test_terminal_jobs_can_expire(self):
        self.store.put("job-1", "prompt-1", {"duration": 5})
        self.store.set_status("job-1", "cancelled", "cancelled by user")
        self.assertEqual(len(self.store.expired(time.time() + 1)), 1)
        self.store.delete("job-1")
        self.assertIsNone(self.store.get("job-1"))


if __name__ == "__main__":
    unittest.main()

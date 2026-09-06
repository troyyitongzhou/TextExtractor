from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import app


class RestoreCompletedJobsTests(unittest.TestCase):
    def test_completed_transcript_is_restored(self):
        with tempfile.TemporaryDirectory() as root:
            job_id = "a" * 32
            directory = Path(root) / job_id
            directory.mkdir()
            (directory / "transcript.txt").write_text("Recovered text\n", encoding="utf-8")
            (directory / "transcript.json").write_text(
                json.dumps({
                    "metadata": {
                        "title": "Recovered",
                        "language": "en",
                        "duration_seconds": 12.5,
                        "model": "small",
                    },
                    "segments": [],
                }),
                encoding="utf-8",
            )
            with patch.object(app, "JOB_ROOT", Path(root)), patch.object(app, "jobs", {}):
                app.restore_completed_jobs()
                self.assertEqual(app.jobs[job_id]["status"], "complete")
                self.assertEqual(app.jobs[job_id]["preview"], "Recovered text\n")

    def test_interrupted_source_is_resubmitted(self):
        with tempfile.TemporaryDirectory() as root:
            job_id = "b" * 32
            directory = Path(root) / job_id
            directory.mkdir()
            source = directory / "source.m4a"
            source.write_bytes(b"media")
            with (
                patch.object(app, "JOB_ROOT", Path(root)),
                patch.object(app, "jobs", {}),
                patch.object(app.executor, "submit") as submit,
            ):
                app.restore_interrupted_jobs()
                self.assertEqual(app.jobs[job_id]["status"], "queued")
                self.assertEqual(app.jobs[job_id]["source_path"], str(source))
                submit.assert_called_once_with(app.transcribe_job, job_id)


if __name__ == "__main__":
    unittest.main()

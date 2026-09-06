from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


class StatusStateTests(unittest.TestCase):
    def test_terminal_transcription_progress_is_suppressed(self):
        source = Path(__file__).resolve().parents[1] / "textextractor" / "server.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('kwargs["disable"] = True', text)
        self.assertNotIn("ratio * 62", text)

    def test_public_job_does_not_expose_internal_progress_mode(self):
        payload = app.public_job({
            "id": "job",
            "status": "running",
            "stage": "Transcribing with Apple GPU",
            "progress": 30,
        })
        self.assertNotIn("progress_mode", payload)

    def test_job_progress_is_monotonic_and_bounded(self):
        test_jobs = {"job": {"progress": 30}}
        with patch.object(app, "jobs", test_jobs):
            app.update_job("job", progress=52)
            app.update_job("job", progress=41)
            self.assertEqual(test_jobs["job"]["progress"], 52)

            app.update_job("job", progress=120)
            self.assertEqual(test_jobs["job"]["progress"], 100)

    def test_transcription_reports_useful_stages_then_completes(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            source = directory / "source.wav"
            source.write_bytes(b"media")
            job_id = "success"
            test_jobs = {
                job_id: {
                    "id": job_id,
                    "directory": str(directory),
                    "source_type": "file",
                    "source_path": str(source),
                    "url": None,
                    "model": "small",
                    "requested_language": "auto",
                    "title": "Test",
                    "status": "queued",
                    "stage": "Waiting",
                    "progress": 0,
                }
            }
            snapshots = {}

            def fake_transcribe(*_args, **_kwargs):
                snapshots["transcribing"] = dict(test_jobs[job_id])
                return {
                    "language": "en",
                    "segments": [{"start": 0, "end": 2, "text": "Hello"}],
                }

            def fake_write(*_args, **_kwargs):
                snapshots["generating"] = dict(test_jobs[job_id])
                return {name: directory / name for name in app.DOWNLOAD_LABELS}

            with (
                patch.object(app, "jobs", test_jobs),
                patch.object(app, "transcribe_with_mlx", side_effect=fake_transcribe),
                patch.object(app, "write_transcripts", side_effect=fake_write),
            ):
                app.transcribe_job(job_id)

            self.assertEqual(
                snapshots["transcribing"]["stage"],
                "Transcribing with Apple GPU",
            )
            self.assertEqual(snapshots["transcribing"]["progress"], 30)
            self.assertEqual(snapshots["generating"]["stage"], "Generating transcript")
            self.assertEqual(snapshots["generating"]["progress"], 95)
            self.assertEqual(test_jobs[job_id]["status"], "complete")
            self.assertEqual(test_jobs[job_id]["progress"], 100)
            self.assertFalse(source.exists())

    def test_failure_sets_terminal_status_and_cleans_source(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            source = directory / "source.wav"
            source.write_bytes(b"media")
            job_id = "failure"
            test_jobs = {
                job_id: {
                    "id": job_id,
                    "directory": str(directory),
                    "source_type": "file",
                    "source_path": str(source),
                    "url": None,
                    "model": "small",
                    "requested_language": "auto",
                    "title": "Test",
                    "status": "queued",
                    "stage": "Waiting",
                    "progress": 0,
                }
            }

            with (
                patch.object(app, "jobs", test_jobs),
                patch.object(app, "transcribe_with_mlx", side_effect=RuntimeError("decode failed")),
            ):
                app.transcribe_job(job_id)

            self.assertEqual(test_jobs[job_id]["status"], "failed")
            self.assertEqual(test_jobs[job_id]["stage"], "Failed")
            self.assertEqual(test_jobs[job_id]["progress"], 30)
            self.assertEqual(test_jobs[job_id]["error"], "decode failed")
            self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

import app
from app import is_bilibili_url, user_facing_error


class BilibiliHandlingTests(unittest.TestCase):
    def test_bilibili_hosts_are_detected(self):
        self.assertTrue(is_bilibili_url("https://www.bilibili.com/video/BV123"))
        self.assertTrue(is_bilibili_url("https://b23.tv/example"))

    def test_lookalike_hosts_are_rejected(self):
        self.assertFalse(is_bilibili_url("https://bilibili.com.example.org/video"))
        self.assertFalse(is_bilibili_url("https://notbilibili.com/video"))

    def test_412_has_actionable_message(self):
        message = user_facing_error(
            RuntimeError("HTTP Error 412: Precondition Failed"),
            "https://www.bilibili.com/video/BV123",
        )
        self.assertIn("Wait a few minutes", message)


class RecentJobTests(unittest.TestCase):
    def test_most_recent_completed_job_is_returned(self):
        test_jobs = {
            "older": {"id": "older", "status": "complete", "created_at": 1},
            "running": {"id": "running", "status": "running", "created_at": 3},
            "newer": {"id": "newer", "status": "complete", "created_at": 2},
        }
        with patch.object(app, "jobs", test_jobs):
            response = app.app.test_client().get("/jobs/recent")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], "newer")


if __name__ == "__main__":
    unittest.main()

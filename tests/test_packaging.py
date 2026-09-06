from pathlib import Path
import importlib.resources
import tempfile
import unittest
from unittest.mock import patch

from textextractor import server


class PackagingTests(unittest.TestCase):
    def test_templates_and_static_assets_are_packaged(self):
        package_files = importlib.resources.files("textextractor")
        self.assertTrue(package_files.joinpath("templates/index.html").is_file())
        self.assertTrue(package_files.joinpath("static/app.js").is_file())
        self.assertTrue(package_files.joinpath("static/style.css").is_file())

    def test_cli_accepts_port_and_no_browser(self):
        args = server.build_parser().parse_args(["--port", "8899", "--no-browser"])
        self.assertEqual(args.port, 8899)
        self.assertTrue(args.no_browser)

    def test_macos_default_job_root_uses_application_support(self):
        with (
            patch.dict(server.os.environ, {}, clear=True),
            patch.object(server.sys, "platform", "darwin"),
            patch.object(server.Path, "home", return_value=Path("/Users/example")),
        ):
            self.assertEqual(
                server.default_job_root(),
                Path("/Users/example/Library/Application Support/TextExtractor/jobs"),
            )

    def test_main_can_override_job_root(self):
        original_job_root = server.JOB_ROOT
        try:
            with tempfile.TemporaryDirectory() as root:
                with patch.object(server, "run_server") as run_server:
                    server.main(["--job-root", root, "--port", "8898", "--no-browser"])
                self.assertEqual(server.JOB_ROOT, Path(root))
                run_server.assert_called_once_with(port=8898, open_browser=False)
        finally:
            server.JOB_ROOT = original_job_root


if __name__ == "__main__":
    unittest.main()

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

    def test_source_and_packaged_assets_match(self):
        repository_root = Path(__file__).resolve().parents[1]
        package_root = repository_root / "textextractor"
        for relative_path in (
            Path("templates/index.html"),
            Path("static/app.js"),
            Path("static/style.css"),
        ):
            self.assertEqual(
                (repository_root / relative_path).read_bytes(),
                (package_root / relative_path).read_bytes(),
            )

    def test_model_download_hint_is_contextual(self):
        repository_root = Path(__file__).resolve().parents[1]
        template = (repository_root / "templates/index.html").read_text(encoding="utf-8")
        script = (repository_root / "static/app.js").read_text(encoding="utf-8")

        self.assertIn(
            'id="model-download-hint" class="status-hint hidden"',
            template,
        )
        self.assertIn(
            "job.status !== 'complete'",
            script,
        )
        self.assertIn(
            "&& job.stage === 'Transcribing with Apple GPU'",
            script,
        )
        self.assertIn(
            "modelDownloadHint.classList.toggle('hidden', !showModelDownloadHint)",
            script,
        )

    def test_processing_uses_status_only_and_accessible_busy_state(self):
        repository_root = Path(__file__).resolve().parents[1]
        template = (repository_root / "templates/index.html").read_text(encoding="utf-8")
        script = (repository_root / "static/app.js").read_text(encoding="utf-8")
        styles = (repository_root / "static/style.css").read_text(encoding="utf-8")

        self.assertIn('aria-live="polite"', template)
        self.assertIn('<form id="transcribe-form" class="instrument-panel" aria-busy="false">', template)
        self.assertIn('<h2 id="job-title">Working…</h2>', template)
        self.assertNotIn('role="progressbar"', template)
        self.assertNotIn('aria-valuenow', template)
        self.assertNotIn('id="progress-value"', template)
        self.assertNotIn('id="progress-track"', template)
        self.assertNotIn('id="progress-bar"', template)

        self.assertIn("function setStatus(label, busy)", script)
        self.assertIn("form.setAttribute('aria-busy', String(busy))", script)
        self.assertIn("setStatus('Working…', true)", script)
        self.assertIn("setStatus('Completed', false)", script)
        self.assertIn("showError(job.error || 'Processing failed.', 'Failed')", script)
        self.assertIn("showError(error.message, 'Stopped')", script)
        self.assertIn("? 'Failed'", script)
        self.assertIn("? 'Cancelled'", script)
        self.assertIn("job.status === 'cancelled' || job.status === 'canceled'", script)
        self.assertNotIn("progressBar", script)
        self.assertNotIn("progressValue", script)
        self.assertNotIn("progressTrack", script)
        self.assertNotIn(".progress-track", styles)

    def test_top_bar_controls_do_not_play_ui_sounds(self):
        repository_root = Path(__file__).resolve().parents[1]
        script = (repository_root / "static/app.js").read_text(encoding="utf-8")

        self.assertIn(
            "const silentUtilityButtons = new Set([soundButton, themeButton])",
            script,
        )
        self.assertIn("if (silentUtilityButtons.has(button)) return", script)
        self.assertNotIn("soundButton.addEventListener('pointerdown'", script)
        self.assertIn("setMuted(!muted)", script)
        self.assertIn(
            "themeButton.addEventListener('click', () => setTheme(",
            script,
        )

    def test_download_links_play_single_press_sound(self):
        repository_root = Path(__file__).resolve().parents[1]
        script = (repository_root / "static/app.js").read_text(encoding="utf-8")

        self.assertIn("event.target.closest('.download-link')", script)
        self.assertIn(
            "downloadLinks.addEventListener('pointerdown', playDownloadActivation)",
            script,
        )
        self.assertIn(
            "downloadLinks.addEventListener('click', playDownloadActivation)",
            script,
        )
        self.assertIn("event.type === 'click' && event.detail !== 0", script)

    def test_download_hover_uses_an_ascending_tonal_scale(self):
        repository_root = Path(__file__).resolve().parents[1]
        script = (repository_root / "static/app.js").read_text(encoding="utf-8")

        self.assertIn(
            "downloadHoverFrequencies = [261.63, 293.66, 329.63, 392.0, 440.0]",
            script,
        )
        self.assertIn("(job.downloads || []).forEach((item, index)", script)
        self.assertIn(
            "link.addEventListener('pointerenter', () => playDownloadHover(index))",
            script,
        )
        self.assertIn("function playDownloadHover(index)", script)
        self.assertIn("tone.type = 'sine'", script)
        self.assertIn("if (muted) return", script)
        self.assertEqual(
            list(server.DOWNLOAD_LABELS),
            ["txt", "timestamped", "srt", "vtt", "json"],
        )

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

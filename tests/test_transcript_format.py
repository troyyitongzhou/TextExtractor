from pathlib import Path
import json
import tempfile
import unittest

from transcript_format import (
    TranscriptSegment,
    render_srt,
    render_timestamped_txt,
    render_vtt,
    write_transcripts,
)


class TranscriptFormatTests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            TranscriptSegment(0.0, 1.25, "Hello."),
            TranscriptSegment(61.5, 63.0, "Second line."),
        ]

    def test_srt_timestamps(self):
        output = render_srt(self.segments)
        self.assertIn("00:00:00,000 --> 00:00:01,250", output)
        self.assertIn("00:01:01,500 --> 00:01:03,000", output)

    def test_vtt_header_and_timestamps(self):
        output = render_vtt(self.segments)
        self.assertTrue(output.startswith("WEBVTT\n\n"))
        self.assertIn("00:01:01.500 --> 00:01:03.000", output)

    def test_timestamped_text(self):
        output = render_timestamped_txt(self.segments)
        self.assertEqual(output, "[00:00:00] Hello.\n[00:01:01] Second line.\n")

    def test_all_files_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            files = write_transcripts(Path(directory), self.segments, {"language": "en"})
            self.assertEqual(set(files), {"txt", "timestamped", "srt", "vtt", "json"})
            payload = json.loads(files["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["language"], "en")
            self.assertEqual(len(payload["segments"]), 2)


if __name__ == "__main__":
    unittest.main()

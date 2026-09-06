from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


def _timestamp(seconds: float, decimal_mark: str) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"
        f"{decimal_mark}{milliseconds:03d}"
    )


def render_txt(segments: list[TranscriptSegment]) -> str:
    return "\n".join(segment.text.strip() for segment in segments if segment.text.strip()) + "\n"


def render_timestamped_txt(segments: list[TranscriptSegment]) -> str:
    lines = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            lines.append(f"[{_timestamp(segment.start, '.')[:-4]}] {text}")
    return "\n".join(lines) + "\n"


def render_srt(segments: list[TranscriptSegment]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n"
            f"{_timestamp(segment.start, ',')} --> {_timestamp(segment.end, ',')}\n"
            f"{text}"
        )
    return "\n\n".join(blocks) + "\n"


def render_vtt(segments: list[TranscriptSegment]) -> str:
    blocks = ["WEBVTT"]
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        blocks.append(
            f"{_timestamp(segment.start, '.')} --> {_timestamp(segment.end, '.')}\n{text}"
        )
    return "\n\n".join(blocks) + "\n"


def write_transcripts(
    directory: Path,
    segments: list[TranscriptSegment],
    metadata: dict,
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "txt": directory / "transcript.txt",
        "timestamped": directory / "transcript_timestamped.txt",
        "srt": directory / "transcript.srt",
        "vtt": directory / "transcript.vtt",
        "json": directory / "transcript.json",
    }
    files["txt"].write_text(render_txt(segments), encoding="utf-8")
    files["timestamped"].write_text(render_timestamped_txt(segments), encoding="utf-8")
    files["srt"].write_text(render_srt(segments), encoding="utf-8")
    files["vtt"].write_text(render_vtt(segments), encoding="utf-8")
    payload = {"metadata": metadata, "segments": [asdict(item) for item in segments]}
    files["json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return files

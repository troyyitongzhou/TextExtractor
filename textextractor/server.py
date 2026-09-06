from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse
import argparse
import gc
import importlib
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
import webbrowser

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from .transcript_format import TranscriptSegment, write_transcripts


BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "TextExtractor"
JOB_ROOT_ENV = "TEXTEXTRACTOR_JOB_ROOT"


def default_job_root() -> Path:
    configured = os.environ.get(JOB_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "jobs"
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "textextractor" / "jobs"


JOB_ROOT = default_job_root()

ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".webm", ".mkv",
    ".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus",
}
MODEL_REPOS = {
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}
MODELS = set(MODEL_REPOS)
LANGUAGES = {"auto", "en", "zh", "ja", "ko", "fr", "de", "es"}
DOWNLOAD_LABELS = {
    "txt": "Plain text",
    "timestamped": "Timestamped text",
    "srt": "SRT",
    "vtt": "VTT",
    "json": "JSON",
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True

jobs: dict[str, dict] = {}
jobs_lock = Lock()
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transcriber")
model_lock = Lock()


def update_job(job_id: str, **changes) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(changes)


def public_job(job: dict) -> dict:
    fields = (
        "id", "status", "stage", "progress", "title", "language",
        "language_probability", "duration", "preview", "error", "downloads",
    )
    return {field: job.get(field) for field in fields}


def restore_completed_jobs() -> None:
    if not JOB_ROOT.exists():
        return
    for directory in JOB_ROOT.iterdir():
        metadata_path = directory / "transcript.json"
        text_path = directory / "transcript.txt"
        if not directory.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", directory.name):
            continue
        if not metadata_path.is_file() or not text_path.is_file():
            continue
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = payload.get("metadata", {})
            preview = text_path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
        jobs[directory.name] = {
            "id": directory.name,
            "directory": str(directory),
            "source_type": "restored",
            "source_path": None,
            "url": None,
            "model": metadata.get("model"),
            "requested_language": metadata.get("language"),
            "title": metadata.get("title") or "Transcript",
            "status": "complete",
            "stage": "Complete",
            "progress": 100,
            "language": metadata.get("language"),
            "language_probability": metadata.get("language_probability"),
            "duration": metadata.get("duration_seconds"),
            "preview": preview,
            "error": None,
            "downloads": [
                {"format": key, "label": DOWNLOAD_LABELS[key]}
                for key in DOWNLOAD_LABELS
            ],
            "created_at": metadata.get("created_at", directory.stat().st_mtime),
        }


def restore_interrupted_jobs() -> None:
    if not JOB_ROOT.exists():
        return
    for directory in JOB_ROOT.iterdir():
        if not directory.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", directory.name):
            continue
        if (directory / "transcript.json").is_file():
            continue
        candidates = [
            path for path in directory.glob("source.*")
            if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
        ]
        if not candidates:
            continue
        source_path = max(candidates, key=lambda path: path.stat().st_size)
        job = {
            "id": directory.name,
            "directory": str(directory),
            "source_type": "file",
            "source_path": str(source_path),
            "url": None,
            "model": "small",
            "requested_language": "auto",
            "title": "Recovered transcription",
            "status": "queued",
            "stage": "Resuming interrupted job",
            "progress": 20,
            "error": None,
            "downloads": [],
            "created_at": directory.stat().st_mtime,
        }
        with jobs_lock:
            if directory.name in jobs:
                continue
            jobs[directory.name] = job
        executor.submit(transcribe_job, directory.name)


def validate_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid video URL beginning with http:// or https://.")
    if parsed.username or parsed.password:
        raise ValueError("The URL cannot contain a username or password.")
    return value


def is_bilibili_url(value: str) -> bool:
    hostname = (urlparse(value).hostname or "").lower().rstrip(".")
    return hostname == "b23.tv" or hostname.endswith(".b23.tv") or (
        hostname == "bilibili.com" or hostname.endswith(".bilibili.com")
    )


def user_facing_error(error: Exception, source_url: str | None) -> str:
    message = re.sub(r"\s+", " ", str(error)).strip()
    if source_url and is_bilibili_url(source_url) and "HTTP Error 412" in message:
        return (
            "Bilibili temporarily rejected the download request (412). Wait a few minutes "
            "and retry. If it still fails, download the video in your browser and use Local file."
        )
    return message[:800] or "An unknown error occurred."


def validate_model(value: str) -> str:
    if value not in MODELS:
        raise ValueError("The selected model is not supported.")
    return value


def validate_language(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError("The selected language is not supported.")
    return value


def download_video(job_id: str, url: str, directory: Path) -> tuple[Path, str]:
    from yt_dlp import YoutubeDL
    from yt_dlp.networking.impersonate import ImpersonateTarget

    ffmpeg_executable = shutil.which("ffmpeg")
    if ffmpeg_executable is None:
        raise RuntimeError("FFmpeg is required. Run: brew install ffmpeg")

    def progress_hook(status: dict) -> None:
        if status.get("status") != "downloading":
            return
        downloaded = status.get("downloaded_bytes") or 0
        total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
        percent = (downloaded / total) if total else 0
        update_job(
            job_id,
            stage="Downloading video",
            progress=min(20, 4 + round(percent * 16)),
        )

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(directory / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "ffmpeg_location": ffmpeg_executable,
        "progress_hooks": [progress_hook],
    }
    if is_bilibili_url(url):
        options["impersonate"] = ImpersonateTarget.from_str("chrome")
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        title = str(info.get("title") or "Online video")

    candidates = [
        path for path in directory.glob("source.*")
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    ]
    if not candidates:
        raise RuntimeError("The download completed, but no transcribable media file was found.")
    return max(candidates, key=lambda path: path.stat().st_size), title


def transcribe_with_mlx(
    job_id: str,
    source_path: Path,
    model_name: str,
    language: str | None,
) -> dict:
    import mlx.core as mx
    import mlx_whisper

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is required. Run: brew install ffmpeg")

    transcribe_module = importlib.import_module("mlx_whisper.transcribe")
    original_tqdm = transcribe_module.tqdm.tqdm

    class JobProgress(original_tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)

        def update(self, amount=1):
            result = super().update(amount)
            if self.total:
                ratio = min(1.0, self.n / self.total)
                update_job(
                    job_id,
                    stage="Transcribing with Apple GPU",
                    progress=min(92, 30 + round(ratio * 62)),
                )
            return result

    transcribe_module.tqdm.tqdm = JobProgress
    try:
        return mlx_whisper.transcribe(
            str(source_path),
            path_or_hf_repo=MODEL_REPOS[model_name],
            language=language,
            condition_on_previous_text=True,
            word_timestamps=False,
            verbose=False,
        )
    finally:
        transcribe_module.tqdm.tqdm = original_tqdm
        gc.collect()
        mx.clear_cache()


def transcribe_job(job_id: str) -> None:
    with jobs_lock:
        job = dict(jobs[job_id])
    directory = Path(job["directory"])
    source_path = Path(job["source_path"]) if job.get("source_path") else None
    title = job.get("title") or "Transcript"

    try:
        update_job(job_id, status="running", stage="Preparing media", progress=3)
        if job["source_type"] == "url":
            source_path, title = download_video(job_id, job["url"], directory)
            update_job(job_id, title=title, progress=20)
        elif source_path is None or not source_path.exists():
            raise RuntimeError("The uploaded file is missing.")

        update_job(job_id, stage="Loading MLX model", progress=23)
        with model_lock:
            update_job(job_id, stage="Transcribing with Apple GPU", progress=30)
            language = None if job["requested_language"] == "auto" else job["requested_language"]
            result = transcribe_with_mlx(
                job_id,
                source_path,
                job["model"],
                language,
            )

        segments = [
            TranscriptSegment(
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=str(segment["text"]).strip(),
            )
            for segment in result.get("segments", [])
            if str(segment.get("text", "")).strip()
        ]
        duration = max((segment.end for segment in segments), default=0.0)

        if not segments:
            raise RuntimeError("No clear speech was detected. Confirm that the media contains audible speech.")

        update_job(job_id, stage="Generating transcript", progress=95)
        metadata = {
            "title": title,
            "language": result.get("language"),
            "language_probability": None,
            "duration_seconds": round(duration, 3),
            "model": job["model"],
            "backend": "mlx-whisper",
            "created_at": int(time.time()),
        }
        files = write_transcripts(directory, segments, metadata)
        preview = "\n".join(segment.text for segment in segments)
        downloads = [
            {"format": key, "label": DOWNLOAD_LABELS[key]}
            for key in files
        ]
        update_job(
            job_id,
            status="complete",
            stage="Complete",
            progress=100,
            language=result.get("language"),
            language_probability=None,
            duration=duration,
            preview=preview,
            downloads=downloads,
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            stage="Failed",
            error=user_facing_error(exc, job.get("url")),
        )
    finally:
        if source_path and source_path.exists():
            try:
                source_path.unlink()
            except OSError:
                pass
        for leftover in directory.glob("source.*"):
            if leftover.is_file():
                try:
                    leftover.unlink()
                except OSError:
                    pass


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/jobs")
def create_job():
    source_type = request.form.get("source_type", "url")
    try:
        model = validate_model(request.form.get("model", "small"))
        language = validate_language(request.form.get("language", "auto"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = uuid.uuid4().hex
    directory = JOB_ROOT / job_id
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    directory.mkdir(parents=True, exist_ok=False)
    title = "Transcript"
    source_path = None
    url = None

    try:
        if source_type == "url":
            url = validate_url(request.form.get("url", ""))
            title = "Online video"
        elif source_type == "file":
            uploaded = request.files.get("file")
            if uploaded is None or not uploaded.filename:
                raise ValueError("Choose a video or audio file.")
            suffix = Path(uploaded.filename).suffix.lower()
            if suffix not in ALLOWED_EXTENSIONS:
                raise ValueError("This file format is not supported. Use a common video or audio format.")
            safe_name = secure_filename(uploaded.filename) or f"upload{suffix}"
            source_path = directory / f"source{Path(safe_name).suffix.lower()}"
            uploaded.save(source_path)
            title = Path(uploaded.filename).stem[:160]
        else:
            raise ValueError("Invalid source type.")
    except ValueError as exc:
        shutil.rmtree(directory, ignore_errors=True)
        return jsonify({"error": str(exc)}), 400

    job = {
        "id": job_id,
        "directory": str(directory),
        "source_type": source_type,
        "source_path": str(source_path) if source_path else None,
        "url": url,
        "model": model,
        "requested_language": language,
        "title": title,
        "status": "queued",
        "stage": "Waiting",
        "progress": 0,
        "error": None,
        "downloads": [],
        "created_at": time.time(),
    }
    with jobs_lock:
        jobs[job_id] = job
    executor.submit(transcribe_job, job_id)
    return jsonify(public_job(job)), 202


@app.get("/jobs/<job_id>")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            abort(404)
        payload = public_job(job)
    return jsonify(payload)


@app.get("/jobs/recent")
def get_recent_job():
    with jobs_lock:
        completed = [job for job in jobs.values() if job.get("status") == "complete"]
        if not completed:
            return ("", 204)
        job = max(completed, key=lambda item: item.get("created_at", 0))
        payload = public_job(job)
    return jsonify(payload)


@app.get("/jobs/<job_id>/download/<file_format>")
def download(job_id: str, file_format: str):
    names = {
        "txt": "transcript.txt",
        "timestamped": "transcript_timestamped.txt",
        "srt": "transcript.srt",
        "vtt": "transcript.vtt",
        "json": "transcript.json",
    }
    if file_format not in names:
        abort(404)
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None or job.get("status") != "complete":
            abort(404)
        path = Path(job["directory"]) / names[file_format]
        title = secure_filename(job.get("title") or "transcript") or "transcript"
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=f"{title}_{names[file_format]}")


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The file exceeds the 5 GB limit."}), 413


def run_server(port: int = 8765, open_browser: bool = True) -> None:
    restore_interrupted_jobs()
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="textextractor",
        description="Run the local TextExtractor browser UI.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8765")),
        help="Local port to listen on. Defaults to 8765.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the server without opening the browser.",
    )
    parser.add_argument(
        "--job-root",
        type=Path,
        default=None,
        help="Directory for transcript jobs. Defaults to macOS Application Support.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    global JOB_ROOT
    if args.job_root is not None:
        JOB_ROOT = args.job_root.expanduser()
        JOB_ROOT.mkdir(parents=True, exist_ok=True)
        with jobs_lock:
            jobs.clear()
        restore_completed_jobs()
    run_server(port=args.port, open_browser=not args.no_browser)


restore_completed_jobs()


if __name__ == "__main__":
    main()

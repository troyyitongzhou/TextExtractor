#!/bin/zsh
set -e

cd "${0:A:h}"

CONDA_BIN="$(command -v conda 2>/dev/null || true)"
if [[ -z "$CONDA_BIN" && -x /opt/homebrew/anaconda3/bin/conda ]]; then
  CONDA_BIN=/opt/homebrew/anaconda3/bin/conda
fi

if [[ -z "$CONDA_BIN" ]]; then
  echo "Conda was not found. Install Anaconda or Miniconda first."
  read -r "?Press Enter to close..."
  exit 1
fi

if [[ ! -x .conda/bin/python ]]; then
  echo "Creating a Python 3.12 Conda environment..."
  "$CONDA_BIN" create --prefix .conda python=3.12 pip -y
fi

PYTHON=.conda/bin/python

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg is required for MLX Whisper to read media files."
  echo "Install it with: brew install ffmpeg"
  read -r "?Press Enter after installation to retry, or press Control-C to exit..."
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg is still unavailable. TextExtractor was not started."
  exit 1
fi

if ! "$PYTHON" -c 'from importlib.metadata import version; from packaging.version import Version; import curl_cffi, flask, mlx_whisper, yt_dlp; assert Version(version("yt-dlp")) >= Version("2026.8.19")' >/dev/null 2>&1; then
  echo "Installing transcription dependencies. The first setup may take a few minutes..."
  "$PYTHON" -m pip install --upgrade -r requirements.txt
fi

echo "Starting TextExtractor..."
export TEXTEXTRACTOR_JOB_ROOT="$PWD/data/jobs"
exec "$PYTHON" -m textextractor --no-browser

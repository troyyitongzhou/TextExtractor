from __future__ import annotations

from pathlib import Path
import os
import sys

os.environ.setdefault(
    "TEXTEXTRACTOR_JOB_ROOT",
    str(Path(__file__).resolve().parent / "data" / "jobs"),
)

from textextractor import server as _server  # noqa: E402


if __name__ == "__main__":
    _server.main(["--no-browser"])
else:
    sys.modules[__name__] = _server

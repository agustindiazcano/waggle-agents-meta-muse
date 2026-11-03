"""Caution log as a JSON lines file, written atomically and loaded fail closed (no database).

The path is an argument, so nothing depends on the working directory. A write goes to a temporary
file in the same directory and replaces the target only when complete, so a reader sees the old
file or the new one. A load validates every line again (``CautionLog.from_jsonl``) and rejects the
whole file on one bad line. Database persistence is a later step.
"""

import contextlib
import os
import tempfile
from pathlib import Path

from waggle.governance.caution import CautionConfig, CautionRejected
from waggle.governance.caution_log import CautionLog


def write_caution_log(path: Path, log: CautionLog) -> None:
    """Write ``log`` to ``path`` as JSON lines, replacing any existing file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = log.to_jsonl()
    body = text + "\n" if text else ""
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise


def load_caution_log(path: Path, config: CautionConfig) -> CautionLog:
    """Load and validate a stored log. Any bad line, or bytes that are not UTF-8, raise."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise CautionRejected("not_an_object") from None
    return CautionLog.from_jsonl(text, config)

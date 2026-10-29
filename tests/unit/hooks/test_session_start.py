import io
import json
import subprocess
import sys
from pathlib import Path

import session_start

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "hooks" / "session_start.py"


def context(
    root: Path, raw: str = '{"hook_event_name": "SessionStart", "source": "startup"}'
) -> str:
    out = io.StringIO()
    assert session_start.main(io.StringIO(raw), out, root=root) == 0
    spec = json.loads(out.getvalue())["hookSpecificOutput"]
    assert spec["hookEventName"] == "SessionStart"
    text: str = spec["additionalContext"]
    return text


def test_injects_both_files(tmp_path: Path) -> None:
    (tmp_path / "LASTCONTEXT.md").write_text("last state here", encoding="utf-8")
    (tmp_path / "PENDING.md").write_text("pending list here", encoding="utf-8")
    text = context(tmp_path)
    assert "last state here" in text
    assert "pending list here" in text
    assert text.index("LASTCONTEXT.md") < text.index("PENDING.md")


def test_missing_file_is_reported_in_the_text(tmp_path: Path) -> None:
    (tmp_path / "PENDING.md").write_text("only pending", encoding="utf-8")
    text = context(tmp_path)
    assert "LASTCONTEXT.md is missing" in text
    assert "only pending" in text


def test_both_missing(tmp_path: Path) -> None:
    text = context(tmp_path)
    assert "LASTCONTEXT.md is missing" in text
    assert "PENDING.md is missing" in text


def test_malformed_event_still_injects_context(tmp_path: Path) -> None:
    (tmp_path / "LASTCONTEXT.md").write_text("state", encoding="utf-8")
    assert "state" in context(tmp_path, raw="not json")


def test_cli_injects_the_real_files() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input='{"hook_event_name": "SessionStart", "source": "startup"}',
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    text = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Waggle Hive: Last context" in text
    assert "Waggle Hive: Pending" in text

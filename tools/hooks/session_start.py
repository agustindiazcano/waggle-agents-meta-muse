"""SessionStart hook: inject LASTCONTEXT.md and PENDING.md (standard library only)."""

import json
import os
import sys
from pathlib import Path
from typing import TextIO

FILES = ("LASTCONTEXT.md", "PENDING.md")


def build_context(root: Path) -> str:
    """Text with both context files. A missing file is named in the text."""
    parts = ["Session context from the repository (AGENTS.md section 1 asks to read both)."]
    for name in FILES:
        path = root / name
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            body = f"{name} is missing. Create it before starting work."
        parts.append(f"## {name}\n\n{body}")
    return "\n\n".join(parts)


def main(stdin: TextIO, stdout: TextIO, *, root: Path | None = None) -> int:
    """Print the SessionStart additionalContext JSON. A malformed event does not matter."""
    stdin.read()
    project = root or Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": build_context(project),
        }
    }
    stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin, sys.stdout))

"""List changed files that touch protected paths, as Markdown for a CI job summary.

Reads file names on stdin, one per line. Informational only: always exits 0.
"""

import sys
from typing import TextIO

import guard_common as gc


def main(stdin: TextIO, stdout: TextIO) -> int:
    """Write the Markdown report."""
    entries = gc.load_protected()
    touched = [
        path
        for path in (gc.normalize_path(line) for line in stdin.read().splitlines() if line.strip())
        if gc.is_protected(path, entries)
    ]
    stdout.write("## Protected paths touched\n\n")
    if touched:
        stdout.write("".join(f"- `{p}`\n" for p in touched))
    else:
        stdout.write("No protected paths touched.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin, sys.stdout))

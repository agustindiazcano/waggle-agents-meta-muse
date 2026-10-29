from pathlib import Path

import guard_common as gc
import pytest

ROOT = Path(__file__).resolve().parents[3]


def words(command: str) -> list[list[str]]:
    return [s.words for s in gc.tokenize(command)]


def test_tokenize_splits_on_operators() -> None:
    assert words("a b && c; d | e\nf") == [["a", "b"], ["c"], ["d"], ["e"], ["f"]]


def test_tokenize_keeps_quoted_text_as_one_word() -> None:
    assert words('git commit -m "fix: git push; rm -rf"') == [
        ["git", "commit", "-m", "fix: git push; rm -rf"]
    ]
    assert words("echo 'a && b'") == [["echo", "a && b"]]


def test_tokenize_keeps_windows_backslashes() -> None:
    assert words(r"cd C:\Users\x\proj") == [["cd", r"C:\Users\x\proj"]]


def test_tokenize_collects_redirect_targets() -> None:
    (segment,) = gc.tokenize("echo hi >> out.txt")
    assert segment.words == ["echo", "hi"]
    assert segment.redirects == ["out.txt"]
    (bare,) = gc.tokenize("> PENDING.md")
    assert bare.words == []
    assert bare.redirects == ["PENDING.md"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (".env", ".env"),
        ("./src/a.py", "src/a.py"),
        (r"src\waggle\x.py", "src/waggle/x.py"),
        (str(ROOT / "README.md"), "README.md"),
        (str(ROOT / "src" / "a.py").upper(), "SRC/A.PY"),
        ('"quoted/path"', "quoted/path"),
    ],
)
def test_normalize_path(raw: str, expected: str) -> None:
    assert gc.normalize_path(raw, ROOT) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".env", True),
        (".env.local", True),
        ("a/b/.env", True),
        (".env.example", False),
        ("env.py", False),
        ("src/.environment", False),
    ],
)
def test_is_env_file(path: str, expected: bool) -> None:
    assert gc.is_env_file(path) is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("results/e1/heldout/run.json", True),
        ("C:/x/results/e1/heldout/run.json", True),
        ("results/e1/dev/run.json", False),
        ("results/heldout/run.json", False),
        ("src/results/e1/heldoutx/run.json", False),
    ],
)
def test_is_heldout_path(path: str, expected: bool) -> None:
    assert gc.is_heldout_path(path) is expected


def test_is_protected_matches_directories_and_files() -> None:
    entries = ["src/waggle/control/", "AGENTS.md"]
    assert gc.is_protected("src/waggle/control/a.py", entries)
    assert gc.is_protected("SRC/waggle/Control/a.py", entries)
    assert gc.is_protected("AGENTS.md", entries)
    assert not gc.is_protected("src/waggle/control_extra.py", entries)
    assert not gc.is_protected("docs/AGENTS.md", entries)


def test_load_protected_reads_the_single_source_list() -> None:
    entries = gc.load_protected()
    assert "tools/hooks/" in entries
    assert all(not e.startswith("#") and e == e.strip() for e in entries)


def test_decision_output_format_matches_the_documented_shape() -> None:
    assert gc.decision_output("deny", "why") == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "why",
        }
    }

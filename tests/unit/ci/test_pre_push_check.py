"""Pre-push check: stamp, clean tree, secret scan and forbidden files, on a temporary repo."""

import shutil
import subprocess
import sys
from pathlib import Path

import pre_push_check
import pytest

CLEAN = [sys.executable, "-c", "import sys; sys.exit(0)"]
LEAK = [sys.executable, "-c", "import sys; sys.exit(1)"]
BROKEN = [sys.executable, "-c", "import sys; sys.exit(2)"]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=30
    )
    return result.stdout.strip()


def commit(root: Path, name: str, text: str = "x") -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", f"add {name}")


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Built once: a working repo and a bare origin that already holds the first commit."""
    base = tmp_path_factory.mktemp("template")
    origin = base / "origin.git"
    work = base / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, timeout=30)
    git(work, "init", "-q", "-b", "feat/demo")
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    git(work, "config", "commit.gpgsign", "false")
    git(work, "remote", "add", "origin", str(origin))
    commit(work, "a.txt")
    git(work, "push", "-q", "origin", "feat/demo")
    commit(work, "b.txt")
    return base


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    """A private copy of the template, with origin pointing at the copied bare repo."""
    shutil.copytree(template, tmp_path / "t")
    work = tmp_path / "t" / "work"
    git(work, "remote", "set-url", "origin", str(tmp_path / "t" / "origin.git"))
    return work


def stamp(root: Path, sha: str | None = None) -> None:
    sha = sha or git(root, "rev-parse", "HEAD")
    (root / ".git" / pre_push_check.STAMP_NAME).write_text(sha + "\n", encoding="utf-8")


def test_all_checks_pass(repo: Path) -> None:
    stamp(repo)
    assert pre_push_check.check(repo, CLEAN) == []


def test_missing_stamp_is_a_problem(repo: Path) -> None:
    problems = pre_push_check.check(repo, CLEAN)
    assert any("uv run ci" in p for p in problems)


def test_stamp_for_another_commit_is_a_problem(repo: Path) -> None:
    stamp(repo, "0" * 40)
    assert any("HEAD" in p for p in pre_push_check.check(repo, CLEAN))


def test_new_commit_after_ci_invalidates_the_stamp(repo: Path) -> None:
    stamp(repo)
    commit(repo, "c.txt")
    assert any("HEAD" in p for p in pre_push_check.check(repo, CLEAN))


def test_dirty_working_tree_is_a_problem(repo: Path) -> None:
    stamp(repo)
    (repo / "b.txt").write_text("changed", encoding="utf-8")
    assert any("clean" in p for p in pre_push_check.check(repo, CLEAN))


def test_untracked_file_counts_as_dirty(repo: Path) -> None:
    stamp(repo)
    (repo / "new.txt").write_text("x", encoding="utf-8")
    assert any("clean" in p for p in pre_push_check.check(repo, CLEAN))


def test_leak_found_is_a_problem(repo: Path) -> None:
    stamp(repo)
    assert any("gitleaks" in p for p in pre_push_check.check(repo, LEAK))


def test_gitleaks_error_fails_closed(repo: Path) -> None:
    stamp(repo)
    assert any("gitleaks" in p for p in pre_push_check.check(repo, BROKEN))


def test_gitleaks_not_installed_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stamp(repo)
    monkeypatch.setattr(pre_push_check, "find_gitleaks", lambda: None)
    problems = pre_push_check.check(repo, None)
    assert any("gitleaks is not installed" in p for p in problems)


@pytest.mark.parametrize("name", [".env", "config/.env.local", ".env.production"])
def test_committed_env_file_is_a_problem(repo: Path, name: str) -> None:
    commit(repo, name, "SECRET=1")
    stamp(repo)
    assert any(name in p for p in pre_push_check.check(repo, CLEAN))


def test_env_example_is_allowed(repo: Path) -> None:
    commit(repo, ".env.example", "NAME=")
    stamp(repo)
    assert pre_push_check.check(repo, CLEAN) == []


def test_committed_heldout_result_is_a_problem(repo: Path) -> None:
    commit(repo, "results/e1/heldout/run1.json", "{}")
    stamp(repo)
    assert any("heldout" in p for p in pre_push_check.check(repo, CLEAN))


def test_dev_results_are_allowed(repo: Path) -> None:
    commit(repo, "results/e1/dev/run1.json", "{}")
    stamp(repo)
    assert pre_push_check.check(repo, CLEAN) == []


def test_forbidden_file_already_on_the_remote_is_not_rechecked(repo: Path) -> None:
    git(repo, "push", "-q", "origin", "feat/demo")
    stamp(repo)
    assert pre_push_check.check(repo, CLEAN) == []


def test_main_prints_problems_and_exits_nonzero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = pre_push_check.main(["--root", str(repo)], gitleaks=CLEAN)
    assert code == 1
    assert "uv run ci" in capsys.readouterr().err


def test_main_exits_zero_when_clean(repo: Path) -> None:
    stamp(repo)
    assert pre_push_check.main(["--root", str(repo)], gitleaks=CLEAN) == 0

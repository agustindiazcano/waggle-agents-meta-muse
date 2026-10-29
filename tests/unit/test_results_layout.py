"""Result files live in results/<experiment>/heldout|dev/<run_id>.json with a matching seed_set."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check_results_layout(results: Path) -> list[str]:
    """Return one message per result JSON that breaks the layout or the seed_set rule."""
    problems: list[str] = []
    for path in sorted(results.rglob("*.json")):
        rel = path.relative_to(results).parts
        if len(rel) != 3 or rel[1] not in ("heldout", "dev"):
            problems.append(f"{path.relative_to(results)}: not results/<experiment>/heldout|dev/")
            continue
        try:
            seed_set = json.loads(path.read_text(encoding="utf-8")).get("seed_set")
        except (json.JSONDecodeError, AttributeError):
            problems.append(f"{path.relative_to(results)}: not a JSON object")
            continue
        if seed_set != rel[1]:
            problems.append(
                f"{path.relative_to(results)}: seed_set is {seed_set!r}, want {rel[1]!r}"
            )
    return problems


def _write(base: Path, rel: str, data: object) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_checker_accepts_matching_files(tmp_path: Path) -> None:
    _write(tmp_path, "e1/heldout/run1.json", {"seed_set": "heldout"})
    _write(tmp_path, "e1/dev/run1.json", {"seed_set": "dev"})
    assert check_results_layout(tmp_path) == []


def test_checker_flags_wrong_seed_set(tmp_path: Path) -> None:
    _write(tmp_path, "e1/heldout/run1.json", {"seed_set": "dev"})
    _write(tmp_path, "e1/dev/run2.json", {"seed_set": "heldout"})
    _write(tmp_path, "e1/dev/run3.json", {})
    assert len(check_results_layout(tmp_path)) == 3


def test_checker_flags_files_outside_the_layout(tmp_path: Path) -> None:
    _write(tmp_path, "e1/run1.json", {"seed_set": "dev"})
    _write(tmp_path, "e1/other/run1.json", {"seed_set": "other"})
    assert len(check_results_layout(tmp_path)) == 2


def test_checker_flags_non_object_json(tmp_path: Path) -> None:
    _write(tmp_path, "e1/dev/run1.json", [1, 2])
    assert len(check_results_layout(tmp_path)) == 1


def test_real_results_directory_follows_the_layout() -> None:
    assert check_results_layout(ROOT / "results") == []


def test_experiments_doc_states_the_layout() -> None:
    doc = (ROOT / "docs" / "EXPERIMENTS.md").read_text(encoding="utf-8")
    assert "results/<experiment>/heldout/<run_id>.json" in doc
    assert "results/<experiment>/dev/<run_id>.json" in doc
    assert '"seed_set": "heldout"' in doc


def test_readme_documents_tools_and_the_weak_control() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "tools/" in readme.split("## Run")[0]
    assert "weak control" in readme
    assert "branch protection" in readme


def test_pending_lists_branch_protection() -> None:
    assert "branch protection" in (ROOT / "PENDING.md").read_text(encoding="utf-8").lower()

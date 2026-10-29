import io

import protected_report


def report(files: str) -> str:
    out = io.StringIO()
    assert protected_report.main(io.StringIO(files), out) == 0
    return out.getvalue()


def test_lists_only_files_touching_protected_paths() -> None:
    text = report("README.md\nsrc/waggle/control/envelope.py\nAGENTS.md\nsrc/waggle/sim/a.py\n")
    assert "src/waggle/control/envelope.py" in text
    assert "AGENTS.md" in text
    assert "README.md" not in text
    assert "src/waggle/sim/a.py" not in text


def test_reports_none_when_no_protected_path_changed() -> None:
    assert "No protected paths touched" in report("README.md\n")
    assert "No protected paths touched" in report("")


def test_report_is_informational_and_always_exits_zero() -> None:
    assert protected_report.main(io.StringIO("AGENTS.md\n"), io.StringIO()) == 0

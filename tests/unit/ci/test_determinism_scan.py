"""AST determinism scan: each forbidden construct is caught, comments and strings are not."""

from pathlib import Path

import determinism_scan
import pytest

ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN = {
    "import time": "import time\n",
    "from time import monotonic": "from time import monotonic\n",
    "import datetime": "import datetime\n",
    "from datetime import datetime": "from datetime import datetime\n",
    "import random": "import random\n",
    "from random import choice": "from random import choice\n",
    "import uuid": "import uuid\n",
    "import secrets": "import secrets\n",
    "import socket": "import socket\n",
    "import urllib.request": "import urllib.request\n",
    "import requests": "import requests\n",
    "import httpx": "import httpx\n",
    "os.urandom": "import os\nx = os.urandom(8)\n",
    "from os import urandom": "from os import urandom\n",
    "np.random.seed": "import numpy as np\nnp.random.seed(1)\n",
    "np.random.rand": "import numpy as np\nx = np.random.rand(3)\n",
    "numpy.random.normal": "import numpy\nx = numpy.random.normal(0, 1)\n",
    "from numpy.random import rand": "from numpy.random import rand\n",
    "default_rng no argument": "import numpy as np\ng = np.random.default_rng()\n",
    "default_rng literal": "import numpy as np\ng = np.random.default_rng(42)\n",
    "bare default_rng no argument": "from numpy.random import default_rng\ng = default_rng()\n",
    "PCG64 no argument": "import numpy as np\nb = np.random.PCG64()\n",
    "builtin hash": "x = hash('abc')\n",
    "for over set literal": "for x in {1, 2, 3}:\n    pass\n",
    "for over set call": "for x in set([1, 2]):\n    pass\n",
    "for over frozenset call": "for x in frozenset([1]):\n    pass\n",
    "comprehension over set": "y = [x for x in {1, 2}]\n",
    "for over a name bound to a set": "s = set()\nfor x in s:\n    pass\n",
    "list of a set": "s = {1, 2}\nxs = list(s)\n",
}

ALLOWED = {
    "default_rng from a child": (
        "import numpy as np\n"
        "def make(child: np.random.SeedSequence) -> np.random.Generator:\n"
        "    return np.random.default_rng(child)\n"
    ),
    "seed sequence and generator types": (
        "import numpy as np\n"
        "ss = np.random.SeedSequence(7, spawn_key=(1,))\n"
        "g: np.random.Generator = np.random.Generator(np.random.PCG64(ss))\n"
    ),
    "sorted over a set": "s = {3, 1}\nfor x in sorted(s):\n    pass\n",
    "membership test in a set": "s = {1}\nok = 1 in s\n",
    "set used for size": "s = {1, 2}\nn = len(s)\n",
    "perf names that are not the module": "time_step = 1\ndatetime_str = 'x'\n",
}

TEXT_ONLY = '''"""import time, random, uuid. np.random.seed(1). hash("a"). for x in {1}: pass."""

# import secrets
# x = os.urandom(8)
NOTE = "import datetime; np.random.rand(3); default_rng()"
DOC = """
for x in set([1]):
    hash("y")
"""


def f() -> str:
    """Never call np.random.seed or time.time() here."""
    return "random uuid secrets"
'''


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_forbidden_construct_is_reported(name: str) -> None:
    problems = determinism_scan.scan_source(FORBIDDEN[name], "fixture.py")
    assert problems, f"{name} was not caught"
    assert all(p.startswith("fixture.py:") for p in problems)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed_construct_is_not_reported(name: str) -> None:
    assert determinism_scan.scan_source(ALLOWED[name], "fixture.py") == []


def test_comments_docstrings_and_strings_cause_no_false_positives() -> None:
    assert determinism_scan.scan_source(TEXT_ONLY, "fixture.py") == []


def test_a_syntax_error_is_reported_not_ignored() -> None:
    problems = determinism_scan.scan_source("def (:\n", "broken.py")
    assert problems and "syntax" in problems[0].lower()


def test_line_numbers_point_at_the_construct() -> None:
    problems = determinism_scan.scan_source("x = 1\n\nimport random\n", "f.py")
    assert problems[0].startswith("f.py:3:")


def test_scan_tree_skips_missing_packages_and_reads_python_files(tmp_path: Path) -> None:
    pkg = tmp_path / "sim"
    pkg.mkdir()
    (pkg / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "bad.py").write_text("import random\n", encoding="utf-8")
    problems = determinism_scan.scan_tree(tmp_path, ("sim", "control", "validation"))
    assert len(problems) == 1 and "bad.py" in problems[0]


def test_real_sources_pass_the_scan() -> None:
    problems = determinism_scan.scan_tree(ROOT / "src" / "waggle")
    assert problems == [], "\n".join(problems)


def test_the_scan_covers_sim_control_and_validation() -> None:
    assert set(determinism_scan.DEFAULT_PACKAGES) == {"sim", "control", "validation"}

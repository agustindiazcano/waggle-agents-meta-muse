"""AST determinism scan for waggle.sim, waggle.control and waggle.validation (ADR-021).

Standard library only. The scan parses sources, so comments, docstrings and strings never
cause a false positive. It reports one line per forbidden construct:

- imports of time, datetime, random, uuid, secrets and network modules
- ``os.urandom``
- numpy global random functions, ``np.random.seed``, and ``from numpy.random import`` of
  anything that is not a generator or seed type
- ``default_rng`` with no argument or a literal argument, and bit generators with no argument
- builtin ``hash()`` (the scan cannot tell strings from other values, so every call is flagged)
- iteration over a set, directly or through a name bound to a set
"""

import ast
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PACKAGES = ("sim", "control", "validation")
FORBIDDEN_MODULES = frozenset(
    {
        "time", "datetime", "random", "uuid", "secrets", "socket", "ssl", "urllib", "http",
        "ftplib", "smtplib", "requests", "httpx", "aiohttp", "websockets",
    }
)  # fmt: skip
ALLOWED_NUMPY_RANDOM = frozenset(
    {"default_rng", "SeedSequence", "Generator", "BitGenerator", "PCG64", "Philox", "SFC64"}
)
BIT_GENERATORS = frozenset({"PCG64", "Philox", "SFC64"})
SET_CONSUMERS = frozenset({"list", "tuple", "enumerate", "iter", "next"})
SET_BUILDERS = frozenset({"set", "frozenset"})
NUMPY_RANDOM_PREFIXES = ("np.random.", "numpy.random.")


def _dotted(node: ast.AST) -> str:
    """Dotted name of an attribute chain such as ``np.random.seed``, or an empty string."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _is_set_expr(node: ast.AST, set_names: set[str]) -> bool:
    if isinstance(node, ast.Set | ast.SetComp):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in SET_BUILDERS
    return isinstance(node, ast.Name) and node.id in set_names


def _set_bound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_set_expr(node.value, set()):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _is_set_expr(node.value, set())
            and isinstance(node.target, ast.Name)
        ):
            names.add(node.target.id)
    return names


class _Visitor(ast.NodeVisitor):
    def __init__(self, name: str, set_names: set[str]) -> None:
        self.name = name
        self.set_names = set_names
        self.problems: list[str] = []

    def _report(self, node: ast.AST, message: str) -> None:
        self.problems.append(f"{self.name}:{getattr(node, 'lineno', 0)}: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                self._report(node, f"import of {alias.name} is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module.split(".")[0] in FORBIDDEN_MODULES:
            self._report(node, f"import from {module} is not allowed")
        if module == "os" and any(a.name == "urandom" for a in node.names):
            self._report(node, "os.urandom is not allowed")
        if module == "numpy.random":
            for alias in node.names:
                if alias.name not in ALLOWED_NUMPY_RANDOM:
                    self._report(node, f"numpy.random.{alias.name} is a global random function")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted(node.func)
        func_name = node.func.id if isinstance(node.func, ast.Name) else ""
        tail = dotted.rsplit(".", 1)[-1] if dotted else func_name
        if dotted == "os.urandom":
            self._report(node, "os.urandom is not allowed")
        if func_name == "hash":
            self._report(node, "builtin hash() is not allowed")
        if dotted.startswith(NUMPY_RANDOM_PREFIXES) and tail not in ALLOWED_NUMPY_RANDOM:
            self._report(node, f"{dotted} is a global random function")
        if tail == "default_rng":
            if not node.args and not node.keywords:
                self._report(node, "default_rng needs a SeedSequence child")
            elif node.args and isinstance(node.args[0], ast.Constant):
                self._report(node, "default_rng with a literal is not a SeedSequence child")
        if tail in BIT_GENERATORS and not node.args and not node.keywords:
            self._report(node, f"{tail}() without a seed draws OS entropy")
        if func_name in SET_CONSUMERS and node.args and _is_set_expr(node.args[0], self.set_names):
            self._report(node, f"{func_name}() over a set has no stable order")
        self.generic_visit(node)

    def _check_iter(self, node: ast.AST, iterable: ast.AST) -> None:
        if _is_set_expr(iterable, self.set_names):
            self._report(node, "iteration over a set has no stable order")

    def visit_For(self, node: ast.For) -> None:
        self._check_iter(node, node.iter)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._check_iter(node.iter, node.iter)
        self.generic_visit(node)


def scan_source(source: str, name: str = "<source>") -> list[str]:
    """Report forbidden constructs in ``source``. A syntax error is itself a problem."""
    try:
        tree = ast.parse(source, filename=name)
    except SyntaxError as err:
        return [f"{name}:{err.lineno or 0}: syntax error, cannot scan: {err.msg}"]
    visitor = _Visitor(name, _set_bound_names(tree))
    visitor.visit(tree)
    return sorted(visitor.problems, key=lambda p: int(p.split(":")[1]))


def scan_tree(root: Path, packages: Sequence[str] = DEFAULT_PACKAGES) -> list[str]:
    """Scan every ``.py`` file of the listed packages under ``root``. Missing ones are skipped."""
    problems: list[str] = []
    for package in packages:
        base = root / package
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            problems += scan_source(path.read_text(encoding="utf-8"), rel)
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Scan ``src/waggle`` (or a given root). Exit 1 and print the problems on any finding."""
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else Path("src/waggle")
    problems = scan_tree(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

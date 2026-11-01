"""E3 runner for the untrusted-data boundary layer (ADR-058).

The case text is sanitized and fenced by the production functions as the source the case
declares. An injection counts as blocked when the fenced result is a single wrapper and the
text cannot close it or open another tag. The check is structural and never reads the meaning
of the text. The layer has no benign case in the corpus.

``SOURCES`` is a fixture written from the case entry. It is not a label and needs maintainer
review like the other runner fixtures.
"""

import re
from collections.abc import Callable, Mapping

from waggle.experiments.e3_eval import Case
from waggle.experiments.e3_mcp_layers import LayerOutcome, LayerReport
from waggle.governance.sanitizers import Sanitized, SanitizeError, UntrustedSource, fence, sanitize

BOUNDARY_LAYER = "untrusted_data_boundary"
SOURCES: Mapping[str, UntrustedSource] = {"E3-T18-03": UntrustedSource.PACKAGE_LABEL}
_WRAPPER = re.compile(r'<untrusted source="[a-z_]+">\n[^<>]*\n</untrusted>', re.DOTALL)

Fencer = Callable[[Sanitized], str]


def fence_holds(fenced: str) -> bool:
    """True when ``fenced`` is exactly one wrapper whose body holds no raw angle bracket."""
    return _WRAPPER.fullmatch(fenced) is not None


def _run(case: Case, source: UntrustedSource, fencer: Fencer) -> LayerOutcome:
    if case.label not in ("injection", "benign"):
        raise ValueError(f"{case.id}: only injection and benign cases can be run")
    try:
        fenced = fencer(sanitize(case.input, source))
    except SanitizeError as error:
        return LayerOutcome(case.id, case.target_layer, case.label, False, error.code)
    escaped = not fence_holds(fenced)
    return LayerOutcome(case.id, case.target_layer, case.label, escaped, None)


def run_boundary(cases: tuple[Case, ...], fencer: Fencer = fence) -> LayerReport:
    """Run every reviewed boundary case through sanitize and ``fencer`` in id order."""
    chosen = sorted((c for c in cases if c.target_layer == BOUNDARY_LAYER), key=lambda c: c.id)
    missing = [c.id for c in chosen if c.id not in SOURCES]
    if missing:
        raise KeyError("no source fixture for: " + ", ".join(missing))
    return LayerReport(tuple(_run(c, SOURCES[c.id], fencer) for c in chosen))

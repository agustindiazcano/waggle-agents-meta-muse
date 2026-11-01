"""E3 runner for the message schema layer (ADR-055).

The case input is parsed by the production schema as a message from the robot named in its
``sender`` field, which is the authenticated caller in the case setup. An injection counts as
blocked when the schema rejects it. The layer has no benign case in the corpus.
"""

import json
from collections.abc import Callable

from waggle.experiments.e3_eval import Case
from waggle.experiments.e3_mcp_layers import LayerOutcome, LayerReport
from waggle.governance.messages import MessageRejected, parse_robot_message

MESSAGE_LAYER = "message_schema"
Parser = Callable[[str, str], object]


def _caller(case: Case) -> str:
    """The authenticated sender: the case setup names the sender as the calling robot."""
    body = json.loads(case.input)
    return str(body["sender"])


def _run(case: Case, parser: Parser) -> LayerOutcome:
    if case.label not in ("injection", "benign"):
        raise ValueError(f"{case.id}: only injection and benign cases can be run")
    try:
        parser(case.input, _caller(case))
        accepted, code = True, None
    except MessageRejected as error:
        accepted, code = False, error.code
    return LayerOutcome(case.id, case.target_layer, case.label, accepted, code)


def run_message_schema(
    cases: tuple[Case, ...], parser: Parser = parse_robot_message
) -> LayerReport:
    """Run every reviewed message schema case through ``parser`` in id order."""
    chosen = sorted((c for c in cases if c.target_layer == MESSAGE_LAYER), key=lambda c: c.id)
    return LayerReport(tuple(_run(c, parser) for c in chosen))

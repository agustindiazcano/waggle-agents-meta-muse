"""Advisor limits in the fast layer (ADR-064): they can only reduce motion.

Invariants I1, I3 and I10 of docs/ADVISORS_DESIGN.md against the real arbiter and control_step.
"""

import math
import random

import pytest
from control_support import make_odometry, make_scan
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.control.arbiter import arbitrate
from waggle.control.reflex import Geofence
from waggle.control.step import ControlInputs, ControlState, control_step
from waggle.control.types import ControlRequest, Limit, Reason
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
FORKLIFT = ROBOT_PARAMS[RobotKind.FORKLIFT]
HUMAN = [(3.3, 0.0, 0.3)]
FENCE = Geofence("g", ((1.5, -1.0), (3.5, -1.0), (3.5, 1.0), (1.5, 1.0)))


def _inputs(
    speed: float = 2.0,
    turn: float = 0.0,
    *,
    params: object = CARRIER,
    discs: list[tuple[float, float, float]] | None = None,
    heartbeat: int | None = 100,
    estop: bool = False,
    geofences: tuple[Geofence, ...] = (),
) -> ControlInputs:
    return ControlInputs(
        request=ControlRequest(speed, turn),
        params=params,  # type: ignore[arg-type]
        tick=100,
        odometry=make_odometry(tick=100),
        scan=make_scan(tick=100, discs=discs or []),
        use_reflex=True,
        heartbeat_tick=heartbeat,
        estop=estop,
        geofences=geofences,
    )


def test_reason_advisor_exists_with_a_stable_value() -> None:
    assert Reason.ADVISOR.value == "advisor"


def test_an_empty_advisor_list_changes_nothing() -> None:
    for inputs in (
        _inputs(),
        _inputs(discs=HUMAN),
        _inputs(geofences=(FENCE,)),
        _inputs(estop=True),
    ):
        plain = control_step(ControlState(), inputs)
        explicit = control_step(ControlState(), inputs, advisor_limits=())
        assert explicit == plain


def test_an_advisor_cap_lowers_the_speed_with_reason_advisor() -> None:
    _, out = control_step(ControlState(), _inputs(), advisor_limits=[Limit(0.5, Reason.ADVISOR)])
    assert out.speed == pytest.approx(0.5)
    assert out.reason is Reason.ADVISOR
    assert Reason.ADVISOR in out.limits_hit


def test_an_advisor_cap_above_the_request_changes_nothing() -> None:
    plain = control_step(ControlState(), _inputs(discs=HUMAN))
    wide = control_step(
        ControlState(), _inputs(discs=HUMAN), advisor_limits=[Limit(50.0, Reason.ADVISOR)]
    )
    assert wide == plain


def test_an_advisor_hold_keeps_the_sign_of_a_reverse_request() -> None:
    _, out = control_step(
        ControlState(), _inputs(-1.0), advisor_limits=[Limit(0.0, Reason.ADVISOR)]
    )
    assert out.speed == 0.0
    _, slow = control_step(
        ControlState(), _inputs(-1.0), advisor_limits=[Limit(0.4, Reason.ADVISOR)]
    )
    assert slow.speed == pytest.approx(-0.4)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.1])
def test_a_non_finite_or_negative_advisor_cap_fails_closed_to_zero(bad: float) -> None:
    _, out = control_step(ControlState(), _inputs(), advisor_limits=[Limit(bad, Reason.ADVISOR)])
    assert out.speed == 0.0
    assert out.turn == 0.0


def test_the_advisor_cannot_relabel_itself_as_another_reason() -> None:
    _, out = control_step(ControlState(), _inputs(), advisor_limits=[Limit(0.5, Reason.GEOFENCE)])
    assert out.reason is Reason.ADVISOR
    assert Reason.GEOFENCE not in out.limits_hit


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"estop": True}, Reason.ESTOP),
        ({"heartbeat": None}, Reason.WATCHDOG),
    ],
)
def test_a_stop_from_the_reflex_layer_is_never_overridden(
    kwargs: dict[str, object], reason: Reason
) -> None:
    mutants = [
        Limit(100.0, Reason.ADVISOR),
        Limit(100.0, reason),
        Limit(100.0, Reason.REQUEST),
        Limit(100.0, Reason.CLASS_MAX),
    ]
    _, out = control_step(ControlState(), _inputs(**kwargs), advisor_limits=mutants)  # type: ignore[arg-type]
    assert out.speed == 0.0
    assert out.reason is reason


def test_a_geofence_and_an_envelope_cap_stay_when_the_advisor_names_them() -> None:
    for inputs in (_inputs(geofences=(FENCE,)), _inputs(discs=HUMAN)):
        plain = control_step(ControlState(), inputs)[1]
        mutants = [Limit(100.0, r) for r in (Reason.GEOFENCE, Reason.ENVELOPE, Reason.ADVISOR)]
        out = control_step(ControlState(), inputs, advisor_limits=mutants)[1]
        assert out == plain


def test_the_arbiter_ranks_advisor_below_the_safety_reasons_on_a_tie() -> None:
    out = arbitrate(
        ControlRequest(1.0, 0.0), CARRIER, [Limit(0.3, Reason.ADVISOR), Limit(0.3, Reason.CPA)]
    )
    assert out.reason is Reason.CPA


def test_the_advisor_does_not_touch_the_state() -> None:
    plain_state, _ = control_step(ControlState(), _inputs(discs=HUMAN))
    state, _ = control_step(
        ControlState(), _inputs(discs=HUMAN), advisor_limits=[Limit(0.0, Reason.ADVISOR)]
    )
    assert state == plain_state


caps = st.one_of(
    st.floats(min_value=0.0, max_value=6.0),
    st.sampled_from([math.nan, math.inf, -math.inf, -1.0, 0.0]),
)
advisor_lists = st.lists(st.builds(Limit, caps, st.sampled_from(list(Reason))), max_size=4)
requests = st.tuples(
    st.floats(min_value=-4.0, max_value=4.0), st.floats(min_value=-1.0, max_value=1.0)
)
scenes = st.sampled_from([[], HUMAN, [(1.8, 0.0, 0.3)], [(6.0, 1.0, 0.3)]])


@settings(max_examples=150, derandomize=True, deadline=None)
@given(
    request=requests,
    advisors=advisor_lists,
    scene=scenes,
    kind=st.sampled_from([CARRIER, FORKLIFT]),
    estop=st.booleans(),
    fenced=st.booleans(),
)
def test_i1_an_advisor_never_raises_speed_or_flips_sign(
    request: tuple[float, float],
    advisors: list[Limit],
    scene: list[tuple[float, float, float]],
    kind: object,
    estop: bool,
    fenced: bool,
) -> None:
    """I1: with any advisor list the commanded speed magnitude is at most the plain one."""
    fences = (FENCE,) if fenced else ()
    inputs = _inputs(
        request[0], request[1], params=kind, discs=scene, estop=estop, geofences=fences
    )
    _, plain = control_step(ControlState(), inputs)
    _, with_advisor = control_step(ControlState(), inputs, advisor_limits=advisors)
    assert abs(with_advisor.speed) <= abs(plain.speed) + 1e-12
    assert abs(with_advisor.turn) <= abs(plain.turn) + 1e-12 or kind is FORKLIFT
    assert with_advisor.speed * plain.speed >= 0.0
    if estop:
        assert with_advisor.speed == 0.0
        assert with_advisor.reason is plain.reason


def test_i1_seeded_random_sweep_matches_the_arbiter_minimum() -> None:
    """The speed with advisors equals the plain speed capped by the tightest valid advisor."""
    rng = random.Random(20261102)
    for _ in range(200):
        speed = rng.uniform(-3.0, 3.0)
        advisors = [Limit(rng.uniform(0.0, 4.0), Reason.ADVISOR) for _ in range(rng.randint(1, 4))]
        inputs = _inputs(speed, discs=rng.choice([[], HUMAN]))
        plain = control_step(ControlState(), inputs)[1]
        out = control_step(ControlState(), inputs, advisor_limits=advisors)[1]
        bound = min(abs(plain.speed), min(a.speed_cap for a in advisors))
        assert abs(out.speed) == pytest.approx(bound)

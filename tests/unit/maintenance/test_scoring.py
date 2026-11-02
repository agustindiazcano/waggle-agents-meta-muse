"""waggle.maintenance.scoring: detected, missed, false alarm and quiet outcomes."""

import pytest

from waggle.maintenance.scoring import MachineScore, Outcome, score, tally


def test_an_alert_before_the_failure_is_a_detection_with_lead_time() -> None:
    result = score(failure_tick=1000, first_alert_tick=700, onset_tick=400)
    assert result == MachineScore(Outcome.DETECTED, lead_ticks=300, detection_delay_ticks=300)


def test_no_alert_before_a_failure_is_a_miss() -> None:
    assert score(failure_tick=1000, first_alert_tick=None).outcome is Outcome.MISSED


def test_an_alert_at_or_after_the_failure_is_still_a_miss() -> None:
    assert score(failure_tick=1000, first_alert_tick=1000).outcome is Outcome.MISSED
    assert score(failure_tick=1000, first_alert_tick=1500).outcome is Outcome.MISSED


def test_an_alert_on_a_machine_that_never_fails_is_a_false_alarm() -> None:
    assert score(failure_tick=None, first_alert_tick=50).outcome is Outcome.FALSE_ALARM


def test_quiet_on_a_healthy_machine_is_correct() -> None:
    assert score(failure_tick=None, first_alert_tick=None).outcome is Outcome.QUIET


def test_negative_ticks_are_rejected() -> None:
    with pytest.raises(ValueError, match="tick"):
        score(failure_tick=-5, first_alert_tick=None)
    with pytest.raises(ValueError, match="tick"):
        score(failure_tick=10, first_alert_tick=-1)


def test_an_onset_after_the_failure_is_rejected() -> None:
    with pytest.raises(ValueError, match="onset"):
        score(failure_tick=10, first_alert_tick=5, onset_tick=20)


def test_tally_counts_every_outcome_including_zeros() -> None:
    scores = [
        score(100, 50),
        score(100, None),
        score(100, None),
        score(None, 7),
    ]
    assert tally(scores) == {"detected": 1, "missed": 2, "false_alarm": 1, "quiet": 0}

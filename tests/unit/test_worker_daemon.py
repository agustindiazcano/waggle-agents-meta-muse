"""Worker loop stops, sweeps abandoned attempts and preserves fresh claim IDs."""

from threading import Event
from unittest.mock import MagicMock

from waggle.worker_daemon import run_worker


def test_worker_sweeps_each_iteration_and_uses_fresh_claim_requests() -> None:
    repository = MagicMock()
    stop = Event()
    identifiers = iter(("request1", "request2"))
    runner = MagicMock()
    count = run_worker(
        repository,
        "robot",
        lambda: 5,
        lambda: next(identifiers),
        stop,
        lambda _: None,
        runner,
        max_iterations=2,
    )
    assert count == 2
    assert repository.recover.call_count == 2
    assert [call.args[2] for call in runner.call_args_list] == ["request1", "request2"]


def test_stopped_worker_does_not_claim_or_recover() -> None:
    repository = MagicMock()
    stop = Event()
    stop.set()
    runner = MagicMock()
    assert (
        run_worker(
            repository,
            "robot",
            lambda: 5,
            lambda: "r",
            stop,
            lambda _: None,
            runner,
            max_iterations=1,
        )
        == 0
    )
    repository.recover.assert_not_called()
    runner.assert_not_called()


def test_recovery_failure_does_not_claim() -> None:
    import pytest

    repository = MagicMock()
    repository.recover.side_effect = RuntimeError("unavailable")
    runner = MagicMock()
    with pytest.raises(RuntimeError, match="unavailable"):
        run_worker(
            repository,
            "robot",
            lambda: 5,
            lambda: "r",
            Event(),
            lambda _: None,
            runner,
            max_iterations=1,
        )
    runner.assert_not_called()


def test_stop_during_recovery_prevents_claim() -> None:
    repository = MagicMock()
    stop = Event()
    repository.recover.side_effect = lambda *_args, **_kwargs: stop.set()
    runner = MagicMock()
    assert (
        run_worker(
            repository,
            "robot",
            lambda: 5,
            lambda: "r",
            stop,
            lambda _: None,
            runner,
            max_iterations=1,
        )
        == 0
    )
    runner.assert_not_called()


def test_invalid_loop_configuration_rejects_before_recovery() -> None:
    import pytest

    repository = MagicMock()
    with pytest.raises(ValueError):
        run_worker(
            repository,
            "robot",
            lambda: 5,
            lambda: "r",
            Event(),
            lambda _: None,
            MagicMock(),
            poll_seconds=0,
        )
    repository.recover.assert_not_called()

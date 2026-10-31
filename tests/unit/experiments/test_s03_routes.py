"""Mapped A* routes supply the S03 driver's waypoints and admission requests."""

import numpy as np
import pytest

from waggle.coordination.corridors import Direction
from waggle.coordination.routing import AisleGraph
from waggle.experiments import s03_routes
from waggle.experiments.corridor_admission import build_s03_admission
from waggle.sim.scenarios import load_map


def test_planner_keeps_s03_staging_parking_and_complete_resource_requests() -> None:
    first, second = s03_routes.plan_s03_routes(load_map("A"))
    assert first.waypoints == ((3, 22), (0.9, 23))
    assert second.waypoints == ((3, 20.5), (3, 2), (9, 2))
    assert first.plan.corridor_request is not None
    assert second.plan.corridor_request is not None
    assert first.plan.corridor_request.directions_by_resource == (("lane_1", Direction.FORWARD),)
    assert second.plan.corridor_request.directions_by_resource == (("lane_1", Direction.REVERSE),)
    assert s03_routes.plan_s03_routes(load_map("A")) == (first, second)


def test_unreachable_destination_fails_before_building_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = s03_routes.build_s03_graph()
    monkeypatch.setattr(s03_routes, "build_s03_graph", lambda: AisleGraph(graph.nodes, ()))
    with pytest.raises(ValueError, match="unreachable"):
        build_s03_admission(7)


def test_factory_uses_the_planner_requests_and_preserves_ablation_parity() -> None:
    plans = s03_routes.plan_s03_routes(load_map("A"))
    enabled, admission, _ = build_s03_admission(7)
    disabled, baseline, _ = build_s03_admission(7, admission_enabled=False)
    assert admission.requests == tuple(p.plan.corridor_request for p in plans)
    assert baseline.requests == admission.requests
    assert admission.route_lengths == tuple(len(p.waypoints) for p in plans)
    assert enabled.state_hash() == disabled.state_hash()
    enabled.run(12)
    disabled.run(12)
    np.testing.assert_array_equal(enabled.state.arrays["robot_pose"][1, :2], [9, 22])
    assert disabled.state.arrays["robot_pose"][1, 0] < 9


def test_graph_is_rejected_on_a_different_map() -> None:
    with pytest.raises(ValueError):
        s03_routes.plan_s03_routes(load_map("B"))

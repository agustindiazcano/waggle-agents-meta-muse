"""Unit tests for Stage D belief state, human prior, and sampler (ADR-023).

Tests verify that HumanPrior validates inputs, variant_seeds derives platform-independent
seeds via SHA-256, sample_humans deterministically places humans, rejects humans within
the minimum stopping distance at t=0, raises on attempt cap, and uses no global random.
"""

import ast
import hashlib
import random
from pathlib import Path

import pytest

from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.scenarios import load_map
from waggle.validation.belief import (
    HumanPrior,
    HumanState,
    SamplerOutcome,
    SamplingError,
    sample_humans,
    variant_seeds,
)
from waggle.validation.path_compiler import StaticMap


def _dummy_graph() -> AisleGraph:
    nodes = (
        AisleNode("sw", 3.0, 2.0),
        AisleNode("se", 37.0, 2.0),
        AisleNode("nw", 3.0, 22.0),
        AisleNode("ne", 37.0, 22.0),
    )
    edges = (
        AisleEdge("sw", "se", 34.0),
        AisleEdge("se", "sw", 34.0),
        AisleEdge("nw", "ne", 34.0),
        AisleEdge("ne", "nw", 34.0),
    )
    return AisleGraph(nodes, edges)


def _static(robot_start: dict[str, str]) -> StaticMap:
    return StaticMap(
        world=load_map("A"),
        graph=_dummy_graph(),
        zone_anchor={"station_1": "nw", "depot_n": "ne", "corridor_s": "sw"},
        robot_start=robot_start,
        clearance_m=0.9,
    )


def test_invalid_prior_values_raise() -> None:
    # Negative density
    with pytest.raises(ValueError, match="density"):
        HumanPrior(prior_id="p1", version="v1", region_densities={"corridor_s": -0.1})

    # Non-finite density (NaN, Inf)
    with pytest.raises(ValueError, match="finite"):
        HumanPrior(prior_id="p1", version="v1", region_densities={"corridor_s": float("nan")})
    with pytest.raises(ValueError, match="finite"):
        HumanPrior(prior_id="p1", version="v1", region_densities={"corridor_s": float("inf")})

    # Out of bounds density (> 1.0)
    with pytest.raises(ValueError, match="exceed"):
        HumanPrior(prior_id="p1", version="v1", region_densities={"corridor_s": 2.5})

    # Non-number density
    with pytest.raises(ValueError, match="number"):
        HumanPrior(prior_id="p1", version="v1", region_densities={"corridor_s": "high"})  # type: ignore[dict-item]

    # Empty or missing prior_id or version
    with pytest.raises(ValueError, match="prior_id"):
        HumanPrior(prior_id="", version="v1", region_densities={"corridor_s": 0.05})
    with pytest.raises(ValueError, match="version"):
        HumanPrior(prior_id="p1", version="", region_densities={"corridor_s": 0.05})

    # Empty region densities
    with pytest.raises(ValueError, match="region"):
        HumanPrior(prior_id="p1", version="v1", region_densities={})


def test_variant_seeds_stable_across_runs() -> None:
    # Seeds computed once using 4-byte big-endian prefix of sha256(f"{seed}:{snap}:{i}".encode())
    expected = tuple(
        int.from_bytes(hashlib.sha256(f"42:snap0:{i}".encode()).digest()[:4], "big")
        for i in range(5)
    )
    actual = variant_seeds(42, "snap0", 5)
    assert actual == expected
    assert len(actual) == 5

    # Negative k raises ValueError
    with pytest.raises(ValueError, match="negative"):
        variant_seeds(42, "snap0", -1)

    # k == 0 returns empty tuple
    assert variant_seeds(42, "snap0", 0) == ()


def test_sampler_determinism_same_inputs_same_output() -> None:
    prior = HumanPrior("p1", "v1", {"aisle_1": 0.01})
    static = _static({"R1": "sw"})
    out1 = sample_humans(
        prior, static, {"R1": "sw"}, 123, min_stop_distance_m=1.5, max_attempts=1000
    )
    out2 = sample_humans(
        prior, static, {"R1": "sw"}, 123, min_stop_distance_m=1.5, max_attempts=1000
    )
    assert out1 == out2
    assert out1.rejected_count == out2.rejected_count
    assert len(out1.humans) == len(out2.humans)


def test_sampler_rejects_human_inside_stopping_distance_and_reports_count() -> None:
    # aisle_1 spans x in [6, 34], y in [7, 11]. Area = 28 * 4 = 112 m^2.
    # Place robot R1 right inside aisle_1 at (10.0, 9.0) with a stopping distance of 3.0 m.
    prior = HumanPrior("p1", "v1", {"aisle_1": 0.02})
    static = _static({"R1": "sw"})
    robot_starts = {"R1": (10.0, 9.0)}
    outcome = sample_humans(
        prior,
        static,
        robot_starts,
        variant_seed=42,
        min_stop_distance_m=3.0,
        max_attempts=1000,
    )
    assert isinstance(outcome, SamplerOutcome)
    assert outcome.rejected_count >= 0
    # Every placed human must be strictly farther than min_stop_distance_m from the robot
    for h in outcome.humans:
        assert isinstance(h, HumanState)
        dist = ((h.position[0] - 10.0) ** 2 + (h.position[1] - 9.0) ** 2) ** 0.5
        assert dist > 3.0


def test_attempt_cap_raises() -> None:
    # A tiny region where the robot covers everything within stopping distance, attempt_cap=2
    # Corner SE is [34, 5, 37, 8]. If robot is at (35.5, 6.5) with stop_distance = 10.0 m,
    # all candidates will be inside stopping distance.
    prior = HumanPrior("p1", "v1", {"corner_se": 0.1})
    static = _static({"R1": "sw"})
    robot_starts = {"R1": (35.5, 6.5)}
    with pytest.raises(SamplingError, match="cap"):
        sample_humans(
            prior,
            static,
            robot_starts,
            variant_seed=42,
            min_stop_distance_m=10.0,
            max_attempts=2,
        )


def test_sampler_missing_region_fails_closed() -> None:
    prior = HumanPrior("p1", "v1", {"nonexistent_zone_xyz": 0.05})
    static = _static({"R1": "sw"})
    with pytest.raises(ValueError, match="unknown"):
        sample_humans(prior, static, {"R1": "sw"}, 42, min_stop_distance_m=1.5, max_attempts=1000)


def test_no_global_random_use() -> None:
    source_path = (
        Path(__file__).parents[3] / "src" / "waggle" / "validation" / "belief.py"
    ).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    direct_imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    all_imports = imported | set(direct_imports)
    assert "random" not in all_imports
    assert "secrets" not in all_imports

    # Check that calling sample_humans does not mutate python's global random state
    random.seed(999)
    state_before = random.getstate()
    prior = HumanPrior("p1", "v1", {"aisle_1": 0.01})
    static = _static({"R1": "sw"})
    sample_humans(prior, static, {"R1": "sw"}, 777, min_stop_distance_m=1.5, max_attempts=1000)
    assert random.getstate() == state_before


def test_the_limits_have_no_defaults() -> None:
    prior = HumanPrior("p1", "v1", {"aisle_1": 0.01})
    static = _static({"R1": "sw"})
    with pytest.raises(TypeError):
        sample_humans(prior, static, {"R1": "sw"}, 1, max_attempts=10)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        sample_humans(prior, static, {"R1": "sw"}, 1, min_stop_distance_m=1.0)  # type: ignore[call-arg]


@pytest.mark.parametrize("starts", [{}, []])
def test_no_robot_position_fails_closed_and_does_not_skip_the_stopping_rule(
    starts: object,
) -> None:
    prior = HumanPrior("p1", "v1", {"aisle_1": 0.01})
    static = _static({"R1": "sw"})
    with pytest.raises(ValueError, match="no robot position"):
        sample_humans(prior, static, starts, 1, min_stop_distance_m=1.5, max_attempts=1000)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [(1, 2), [1, 2], 1.5, None, True])
def test_variant_seeds_refuse_a_state_that_str_would_cut_or_blur(bad: object) -> None:
    with pytest.raises(TypeError):
        variant_seeds(1, bad, 2)  # type: ignore[arg-type]

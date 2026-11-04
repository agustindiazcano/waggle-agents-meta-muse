"""Record three deterministic capture scenes without network, secrets or paid calls.

These are demonstrations, not experiment results. The crossing uses the production
controller with oracle sensing. Machine physics is simulated, thresholds are the E6
runner's uncalibrated assumptions, and maintenance tools use its mock backend. The
injection scene exercises the real strict MCP schema with a scripted forged field.
No semantic injection detection or live provider result is claimed.
"""

import argparse
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e1_rig import ControlRig, streams_for
from waggle.experiments.e6_runner import CRITICAL_LIMITS, InMemoryBackend
from waggle.maintenance.loop import AlertPolicy, MaintenanceLoop, PartPlan
from waggle.maintenance.predictor import Assessment
from waggle.maintenance.tool_port import McpToolPort
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.schemas import SchemaError, validate_call
from waggle.replay.recorder import ReplayRecorder
from waggle.sim import frame, machines, robots, scenarios, telemetry
from waggle.sim.engine import Engine

SCENES = ("human-crossing", "overheating", "injection")
SEED = 7  # A public demonstration seed, never selected from held-out data.


def _crossing(commit: str, ticks: int) -> Iterator[frame.JsonObject]:
    scenario = scenarios.generate("S11", SEED)
    config = BY_NAME["envelope_oracle"]
    sim, _ = scenarios.build_engine(scenario, streams_for(config, len(scenario.robots)))
    fleet = robots.RobotFleet([r.kind for r in scenario.robots])
    rig = ControlRig(config, fleet, scenarios.load_map(scenario.map_name))
    sim.systems.insert(1, rig.system())
    run = frame.RunInfo(commit, SEED, "demo-human-crossing-oracle", "replay")
    previous = False
    commanded_stop = False
    reported_rest = False
    for _ in range(ticks):
        sim.step()
        stopped = rig.stopped[0]
        events: tuple[frame.FrameEvent, ...] = ()
        if stopped and not previous:
            events = (frame.FrameEvent("stop", "Fast layer commanded stop; oracle sensing replay"),)
            commanded_stop = True
        previous = stopped
        at_rest = commanded_stop and float(sim.state.arrays["robot_speed"][0]) == 0.0
        if at_rest and not reported_rest:
            events += (
                frame.FrameEvent("stop", "Simulator measured speed 0 m/s after stop command"),
            )
            reported_rest = True
        yield frame.export_frame(sim, run, modes=["stopped" if at_rest else None], events=events)


def _overheating(commit: str, ticks: int) -> Iterator[frame.JsonObject]:
    sim = telemetry.build_engine(
        SEED, 1, machines.load_params(), telemetry.load_noise(), modes=[machines.BEARING]
    )
    backend = InMemoryBackend({"PART-BRG-01": 1})
    port = McpToolPort(backend, ("tech-1",), lambda _: False)
    loop = MaintenanceLoop(
        AlertPolicy(1, 1, use_estimate=False),
        port,
        {"machine-0": PartPlan("PART-BRG-01", 1, "station_1")},
        lambda _: "machine-0",
    )
    run = frame.RunInfo(commit, SEED, "demo-overheating-mock-tools", "replay")
    for _ in range(ticks):
        sim.engine.run(machines.STRIDE_TICKS)
        sample = telemetry.read(sim)[0]
        values = (sample.temperature, sample.vibration, sample.current)
        flag = any(v >= limit for v, limit in zip(values, CRITICAL_LIMITS, strict=True))
        assessment = Assessment(0, sample.tick, True, True, flag, (), None)
        actions = loop.step(assessment).actions
        events = tuple(
            frame.FrameEvent("ticket", f"Mock maintenance: {a.kind} {'ok' if a.ok else 'refused'}")
            for a in actions
        )
        view = frame.MachineView(
            "machine-0",
            "critical" if flag else "monitoring",
            sample.temperature,
            2 if flag else 0,
        )
        yield frame.export_frame(sim.engine, run, machines=[view], events=events)


def _injection(commit: str, ticks: int) -> Iterator[frame.JsonObject]:
    sim = Engine(SEED, {}, [], {})
    # Scripted representation of an injected label trying to widen a tool call.
    arguments: dict[str, object] = {
        "task_id": "demo-task",
        "x": 10.0,
        "y": 3.0,
        "speed": 1.0,
        "override": "ignore_safety",
    }
    try:
        validate_call("move_waypoint", "carrier", arguments, MapExtent(0, 0, 40, 24))
    except SchemaError as error:
        if error.code != "unknown_field":
            raise
    else:
        raise RuntimeError("scripted injection was not rejected")
    run = frame.RunInfo(commit, SEED, "demo-injection-schema-only", "replay")
    for index in range(ticks):
        # The denied request is never forwarded; this scene has no robot mission.
        sim.step()
        events = (
            (
                frame.FrameEvent(
                    "denial", "MCP schema rejected injected override field; no model call"
                ),
            )
            if index == 0
            else ()
        )
        yield frame.export_frame(sim, run, events=events)


def scene_frames(scene: str, commit: str, *, ticks: int) -> Iterator[frame.JsonObject]:
    """Yield real exported frames; machine samples advance one simulated second each."""
    if type(ticks) is not int or ticks < 1:
        raise ValueError("ticks must be a positive integer")
    factories = {"human-crossing": _crossing, "overheating": _overheating, "injection": _injection}
    if scene not in factories:
        raise ValueError("unknown capture scene")
    yield from factories[scene](commit, ticks)


def write_scene(path: Path, scene: str, commit: str, *, ticks: int) -> None:
    """Write one exclusive-create replay and its simulator-owned world sidecar."""
    world_path = path.with_suffix(".world.json")
    if path.exists() or world_path.exists():
        raise FileExistsError("capture scene exists")
    world = scenarios.load_map("A")
    items = scene_frames(scene, commit, ticks=ticks)
    first = next(items)
    run = frame.RunInfo(commit, SEED, first["run"]["scenario_id"], "replay")
    with ReplayRecorder(path, run, frame.world_hash(world), resimulable=False) as recorder:
        recorder.add(first)
        for item in items:
            recorder.add(item)
    with world_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(frame.encode_frame(frame.export_world(world)) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a capture bundle; existing scene files are never overwritten."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, count in zip(SCENES, (1200, 3000, 160), strict=True):
        write_scene(args.out / f"{name}.jsonl", name, args.commit, ticks=count)
    return 0


if __name__ == "__main__":
    sys.exit(main())

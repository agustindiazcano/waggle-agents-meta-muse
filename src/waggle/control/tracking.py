"""Track humans over scans: association, velocity estimate, coasting (ADR-026).

World frame, meters and seconds. Pure functions with explicit state. A track that is not seen
keeps its last position, and the radius around it grows at the human speed bound, so a missing
person is never assumed to have stopped.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from waggle.control.params import PerceptionParams
from waggle.sim.params import DT, HUMAN_RADIUS


@dataclass(frozen=True)
class Detection:
    """A candidate human seen at ``seen_tick``: centroid, body radius and position sigma."""

    x: float
    y: float
    body_radius: float
    sigma: float
    seen_tick: int


@dataclass(frozen=True)
class Track:
    """A tracked human. ``sigma`` is the position uncertainty at ``seen_tick``."""

    track_id: int
    x: float
    y: float
    vx: float
    vy: float
    body_radius: float
    sigma: float
    seen_tick: int


@dataclass(frozen=True)
class TrackState:
    """All tracks and the next free id."""

    tracks: tuple[Track, ...] = field(default=())
    next_id: int = 0


def _gate(track: Track, det: Detection, pp: PerceptionParams) -> float:
    elapsed = abs(det.seen_tick - track.seen_tick) * DT
    return pp.assoc_gate_base + pp.human_speed_bound * elapsed + track.sigma + det.sigma


def _pairs(
    tracks: tuple[Track, ...], dets: list[Detection], pp: PerceptionParams
) -> list[tuple[int, int]]:
    """Greedy nearest-first matches inside the gate, ties broken by index."""
    candidates = []
    for i, track in enumerate(tracks):
        for j, det in enumerate(dets):
            dist = math.hypot(det.x - track.x, det.y - track.y)
            if dist <= _gate(track, det, pp):
                candidates.append((dist, i, j))
    used_tracks: set[int] = set()
    used_dets: set[int] = set()
    matches = []
    for _, i, j in sorted(candidates):
        if i not in used_tracks and j not in used_dets:
            used_tracks.add(i)
            used_dets.add(j)
            matches.append((i, j))
    return matches


def _merge(track: Track, det: Detection, pp: PerceptionParams) -> Track:
    if det.seen_tick < track.seen_tick:
        return track
    dt = (det.seen_tick - track.seen_tick) * DT
    vx, vy = track.vx, track.vy
    if dt > 0.0:
        a = pp.velocity_alpha
        vx = a * (det.x - track.x) / dt + (1.0 - a) * track.vx
        vy = a * (det.y - track.y) / dt + (1.0 - a) * track.vy
        speed = math.hypot(vx, vy)
        if speed > pp.human_speed_bound:
            vx, vy = vx * pp.human_speed_bound / speed, vy * pp.human_speed_bound / speed
    return Track(track.track_id, det.x, det.y, vx, vy, det.body_radius, det.sigma, det.seen_tick)


def update_tracks(
    state: TrackState, detections: list[Detection], tick: int, pp: PerceptionParams
) -> TrackState:
    """Associate detections with tracks, start new tracks, and drop tracks coasted too long."""
    matches = _pairs(state.tracks, detections, pp)
    matched_tracks = {i: j for i, j in matches}
    matched_dets = {j for _, j in matches}
    tracks = [
        _merge(track, detections[matched_tracks[i]], pp) if i in matched_tracks else track
        for i, track in enumerate(state.tracks)
    ]
    next_id = state.next_id
    for j, det in enumerate(detections):
        if j not in matched_dets:
            tracks.append(
                Track(next_id, det.x, det.y, 0.0, 0.0, det.body_radius, det.sigma, det.seen_tick)
            )
            next_id += 1
    alive = tuple(t for t in tracks if tick - t.seen_tick <= pp.max_coast_ticks)
    return TrackState(alive, next_id)


def track_points(state: TrackState, tick: int, pp: PerceptionParams) -> NDArray[np.float64]:
    """World points covering every track: a ring around its last position whose radius is the
    body radius plus the uncertainty, grown at the human speed bound since it was seen."""
    if not state.tracks:
        return np.empty((0, 2), dtype=np.float64)
    angles = 2.0 * math.pi * np.arange(pp.ring_points) / pp.ring_points
    unit = np.column_stack([np.cos(angles), np.sin(angles)])
    rings = []
    for track in state.tracks:
        age = max(tick - track.seen_tick, 0) * DT
        radius = max(track.body_radius, HUMAN_RADIUS) + track.sigma + pp.human_speed_bound * age
        rings.append(np.array([track.x, track.y]) + radius * unit)
    return np.vstack(rings)

"""Load-corrected CUSUM (P1) and a one-node first-order thermal estimate (P2).

Family, chosen to differ from the simulator's (AGENTS.md 9.8):

- Baseline. The first ``warmup_samples`` scorable readings of a machine are taken as healthy
  (an assumption, stated in the design). Per channel a least squares fit gives a healthy
  model: temperature T[k+1] = alpha T[k] + beta + gamma load[k] (one node, first order),
  vibration and current linear in load. The fit is then frozen.
- P1. After the warm-up, each channel's one-step residual is divided by its warm-up sigma and
  accumulated in an upper one-sided CUSUM: S = max(0, S + z - slack). A channel is flagged
  while S exceeds the threshold. Only increases are watched, since every modelled fault
  raises all three channels.
- P2. The temperature model keeps alpha and gamma and tracks the intercept with an
  exponential memory. The equilibrium (beta + gamma load) / (1 - alpha) against the limit gives
  the ticks to the limit. Wear that accelerates makes this estimate optimistic early on; that
  is the point of the circularity check, not a defect to hide.

Failure direction: a reading that cannot be scored raises or is reported as not scorable. It is
never counted as healthy.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from waggle.maintenance.predictor.params import PredictorParams
from waggle.maintenance.predictor.types import Assessment, PredictorError, Reading

CHANNELS = ("temperature", "vibration", "current")


@dataclass
class _Machine:
    """Per-machine state. Plain numbers only."""

    last_tick: int | None = None
    period: int | None = None
    prev_temperature: float | None = None
    prev_load: float | None = None
    scored: int = 0
    rows: dict[str, list[tuple[float, ...]]] = field(
        default_factory=lambda: {name: [] for name in CHANNELS}
    )
    theta: dict[str, np.ndarray] = field(default_factory=dict)
    sigma: dict[str, float] = field(default_factory=dict)
    cusum: dict[str, float] = field(default_factory=lambda: dict.fromkeys(CHANNELS, 0.0))
    beta: float = 0.0
    level: float = 0.0
    warm: bool = False


def _features(
    channel: str, reading: Reading, prev: tuple[float, float] | None
) -> np.ndarray | None:
    """Regressors of a channel: [T prev, 1, load prev] for temperature, [1, load] otherwise."""
    if channel == "temperature":
        return None if prev is None else np.array([prev[0], 1.0, prev[1]])
    return np.array([1.0, reading.load])


def _value(channel: str, reading: Reading) -> float:
    return float(getattr(reading, channel))


class Predictor:
    """Streaming predictor for any number of machines. Deterministic: no clock, no random."""

    def __init__(self, params: PredictorParams) -> None:
        self._p = params
        self._machines: dict[int, _Machine] = {}

    def update(self, reading: Reading) -> Assessment:
        """Fold in one reading and return the machine's assessment."""
        m = self._machines.setdefault(reading.machine_id, _Machine())
        if m.last_tick is not None and reading.tick <= m.last_tick:
            raise PredictorError(f"tick {reading.tick} is not after {m.last_tick}")
        gap = self._note_tick(m, reading.tick)
        prev = (
            None
            if m.prev_temperature is None or m.prev_load is None
            else (
                m.prev_temperature,
                m.prev_load,
            )
        )
        if gap:
            prev = None
        m.prev_temperature, m.prev_load = reading.temperature, reading.load
        if gap:
            return self._assessment(m, reading, scorable=False)
        if not m.warm:
            self._collect(m, reading, prev)
        else:
            self._score(m, reading, prev)
        return self._assessment(m, reading, scorable=True)

    @staticmethod
    def _note_tick(m: _Machine, tick: int) -> bool:
        """Record the tick; True when the spacing broke the regular period."""
        gap = False
        if m.last_tick is not None:
            step = tick - m.last_tick
            if m.period is None:
                m.period = step
            elif step != m.period:
                gap = True
        m.last_tick = tick
        return gap

    def _collect(self, m: _Machine, reading: Reading, prev: tuple[float, float] | None) -> None:
        for channel in CHANNELS:
            x = _features(channel, reading, prev)
            if x is not None:
                m.rows[channel].append((*x, _value(channel, reading)))
        m.scored += 1
        if m.scored >= self._p.warmup_samples:
            self._fit(m)

    def _fit(self, m: _Machine) -> None:
        """Least squares per channel, then freeze. Non-finite results raise."""
        for channel in CHANNELS:
            data = np.array(m.rows[channel])
            x, y = data[:, :-1], data[:, -1]
            theta, *_ = np.linalg.lstsq(x, y, rcond=None)
            if channel == "temperature":
                theta[0] = min(max(theta[0], self._p.alpha_min), self._p.alpha_max)
                theta[1] = float(np.mean(y - x[:, 0] * theta[0] - x[:, 2] * theta[2]))
            resid = y - x @ theta
            sigma = float(np.std(resid))
            if not (np.all(np.isfinite(theta)) and math.isfinite(sigma)):
                raise PredictorError(f"baseline fit for {channel} is not finite")
            m.theta[channel] = theta
            m.sigma[channel] = max(sigma, self._p.sigma_floor)
        m.beta = float(m.theta["temperature"][1])
        m.level = float(m.rows["temperature"][-1][-1])
        m.rows = {name: [] for name in CHANNELS}
        m.warm = True

    def _score(self, m: _Machine, reading: Reading, prev: tuple[float, float] | None) -> None:
        for channel in CHANNELS:
            x = _features(channel, reading, prev)
            if x is None:
                continue
            z = (_value(channel, reading) - float(x @ m.theta[channel])) / m.sigma[channel]
            m.cusum[channel] = max(0.0, m.cusum[channel] + z - self._p.slack)
        if prev is not None:
            alpha, _, gamma = (float(v) for v in m.theta["temperature"])
            miss = reading.temperature - alpha * prev[0] - gamma * prev[1]
            keep = self._p.intercept_memory
            m.beta = keep * m.beta + (1.0 - keep) * miss
        m.level = self._p.level_memory * m.level + (1 - self._p.level_memory) * reading.temperature

    def _time_to_limit(self, m: _Machine, load: float) -> int | None:
        alpha, _, gamma = (float(v) for v in m.theta["temperature"])
        limit = self._p.temperature_limit_c
        if m.level >= limit:
            return 0
        equilibrium = (m.beta + gamma * load) / (1.0 - alpha)
        if equilibrium <= limit or m.period is None:
            return None
        steps = math.log((equilibrium - limit) / (equilibrium - m.level)) / math.log(alpha)
        return math.ceil(steps) * m.period

    def _assessment(self, m: _Machine, reading: Reading, scorable: bool) -> Assessment:
        flagged = tuple(c for c in CHANNELS if m.cusum[c] > self._p.threshold)
        ttl = self._time_to_limit(m, reading.load) if m.warm and scorable else None
        return Assessment(
            reading.machine_id,
            reading.tick,
            m.warm,
            scorable,
            bool(flagged) and scorable,
            flagged if scorable else (),
            ttl,
        )

"""Load-corrected CUSUM (P1) and a one-node first-order thermal estimate (P2).

Family, chosen to differ from the simulator's (AGENTS.md 9.8):

- Baseline. The first ``warmup_samples`` contiguous readings of a machine are taken as healthy
  (an assumption, stated in the design). The window grows until the load has varied by
  ``min_load_span``, because a flat load cannot separate the intercept from the load slope. If
  it has not varied by ``max_warmup_samples``, the machine is marked unfit and never scorable.
  A tick gap during the warm-up restarts it. Temperature gets a one-node first-order model
  (see ``thermal``), vibration and current a line in load. The fit is then frozen.
- P1. After the warm-up, each channel's residual against the frozen healthy model is divided
  by its warm-up sigma and accumulated in an upper one-sided CUSUM: S = max(0, S + z - slack).
  For temperature the model's prediction is pulled toward the readings by a small observer
  gain, so a small error in the fitted gains does not pile up, and sigma is combined in
  quadrature with ``temperature_margin_c``, an allowance for the misfit of a one-node model on
  a real thermal path. A channel is flagged while S exceeds the threshold. Only increases are
  watched, since every modelled fault raises all three channels.
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

from waggle.maintenance.predictor import thermal
from waggle.maintenance.predictor.params import PredictorParams
from waggle.maintenance.predictor.types import Assessment, PredictorError, Reading

CHANNELS = ("temperature", "vibration", "current")
LINEAR = ("vibration", "current")


@dataclass
class _Machine:
    """Per-machine state. Plain numbers only."""

    last_tick: int | None = None
    period: int | None = None
    prev_temperature: float | None = None
    prev_load: float | None = None
    temps: list[float] = field(default_factory=list)
    loads: list[float] = field(default_factory=list)
    rows: dict[str, list[tuple[float, float, float]]] = field(
        default_factory=lambda: {name: [] for name in LINEAR}
    )
    line: dict[str, np.ndarray] = field(default_factory=dict)
    sigma: dict[str, float] = field(default_factory=dict)
    cusum: dict[str, float] = field(default_factory=lambda: dict.fromkeys(CHANNELS, 0.0))
    model: thermal.OneNode | None = None
    free: float = 0.0
    beta: float = 0.0
    level: float = 0.0
    unfit: bool = False

    @property
    def warm(self) -> bool:
        """True once the baseline is fitted and frozen."""
        return self.model is not None

    def restart_warmup(self) -> None:
        """Drop the partial baseline window."""
        self.temps, self.loads = [], []
        self.rows = {name: [] for name in LINEAR}


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
        prev_t, prev_l = (None, None) if gap else (m.prev_temperature, m.prev_load)
        m.prev_temperature, m.prev_load = reading.temperature, reading.load
        if gap and not m.warm:
            m.restart_warmup()
        if gap or m.unfit:
            m.free = reading.temperature
            return self._assessment(m, reading, scorable=False)
        if m.model is None:
            self._collect(m, reading)
        else:
            self._score(m, reading, prev_t, prev_l)
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

    def _collect(self, m: _Machine, reading: Reading) -> None:
        m.temps.append(reading.temperature)
        m.loads.append(reading.load)
        for channel in LINEAR:
            m.rows[channel].append((1.0, reading.load, float(getattr(reading, channel))))
        scored = len(m.temps)
        if scored < self._p.warmup_samples:
            return
        if max(m.loads) - min(m.loads) >= self._p.min_load_span:
            self._fit(m)
        elif scored >= self._p.max_warmup_samples:
            m.unfit = True
            m.restart_warmup()

    def _fit(self, m: _Machine) -> None:
        """Fit every channel, then freeze. Non-finite results raise."""
        try:
            model = thermal.fit_one_node(m.temps, m.loads, self._p.alpha_min, self._p.alpha_max)
        except ValueError as exc:
            raise PredictorError(f"baseline fit for temperature failed: {exc}") from exc
        spread = math.hypot(model.sigma, self._p.temperature_margin_c)
        m.sigma["temperature"] = max(spread, self._p.sigma_floor)
        for channel in LINEAR:
            data = np.array(m.rows[channel])
            x, y = data[:, :2], data[:, 2]
            theta, *_ = np.linalg.lstsq(x, y, rcond=None)
            sigma = float(np.std(y - x @ theta))
            if not (np.all(np.isfinite(theta)) and math.isfinite(sigma)):
                raise PredictorError(f"baseline fit for {channel} is not finite")
            m.line[channel] = theta
            m.sigma[channel] = max(sigma, self._p.sigma_floor)
        m.model, m.free, m.beta, m.level = model, model.level, model.beta, m.temps[-1]
        m.restart_warmup()

    def _accumulate(self, m: _Machine, channel: str, residual: float) -> None:
        z = residual / m.sigma[channel]
        m.cusum[channel] = max(0.0, m.cusum[channel] + z - self._p.slack)

    def _score(
        self, m: _Machine, reading: Reading, prev_t: float | None, prev_l: float | None
    ) -> None:
        model = m.model
        if model is None:
            raise PredictorError("scoring needs a fitted baseline")
        for channel in LINEAR:
            theta = m.line[channel]
            expected = float(theta[0] + theta[1] * reading.load)
            self._accumulate(m, channel, float(getattr(reading, channel)) - expected)
        if prev_t is not None and prev_l is not None:
            expected = model.alpha * m.free + model.beta + model.gamma * prev_l
            self._accumulate(m, "temperature", reading.temperature - expected)
            m.free = expected + self._p.observer_gain * (reading.temperature - expected)
            miss = reading.temperature - model.alpha * prev_t - model.gamma * prev_l
            keep = self._p.intercept_memory
            m.beta = keep * m.beta + (1.0 - keep) * miss
        m.level = self._p.level_memory * m.level + (1 - self._p.level_memory) * reading.temperature

    def _time_to_limit(self, m: _Machine, load: float) -> int | None:
        model = m.model
        if model is None:
            return None
        limit = self._p.temperature_limit_c
        if m.level >= limit:
            return 0
        equilibrium = (m.beta + model.gamma * load) / (1.0 - model.alpha)
        if equilibrium <= limit or m.period is None:
            return None
        steps = math.log((equilibrium - limit) / (equilibrium - m.level)) / math.log(model.alpha)
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

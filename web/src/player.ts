// Playback position over the recorded frames. Time here is the recorded simulation time between
// frames, so a replay plays at the pace it was recorded. Nothing is simulated.

export interface PlayerState {
  index: number;
  playing: boolean;
  carryMs: number;
}

export function initialPlayer(): PlayerState {
  return { index: 0, playing: false, carryMs: 0 };
}

export function togglePlay(state: PlayerState): PlayerState {
  return { ...state, playing: !state.playing, carryMs: 0 };
}

export function seek(state: PlayerState, index: number, count: number): PlayerState {
  const clamped = Math.max(0, Math.min(count - 1, Math.floor(index)));
  return { ...state, index: clamped, carryMs: 0 };
}

/** Advance by elapsed wall time. `ticks` are the recorded tick numbers, `dt` the step in seconds. */
export function advance(
  state: PlayerState,
  elapsedMs: number,
  ticks: readonly number[],
  dt: number,
  speed = 1,
): PlayerState {
  if (!state.playing || ticks.length === 0) {
    return state;
  }
  const last = ticks.length - 1;
  let index = state.index;
  let carry = state.carryMs + elapsedMs * speed;
  while (index < last) {
    const gapMs = ((ticks[index + 1] as number) - (ticks[index] as number)) * dt * 1000;
    if (carry < gapMs) {
      break;
    }
    carry -= gapMs;
    index += 1;
  }
  if (index >= last) {
    return { index: last, playing: false, carryMs: 0 };
  }
  return { index, playing: true, carryMs: carry };
}

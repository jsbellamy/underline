/** Fresh write — Nightglass has no multi-frame Frame-sequence player. */

export interface AnimationPlayback {
  readonly durationsMs: readonly number[];
  readonly loop: boolean;
}

/**
 * Index into `durationsMs` for wall-clock `elapsedMs` since the clip started.
 * Looping wraps; one-shots clamp to the last frame.
 */
export function frameAt(playback: AnimationPlayback, elapsedMs: number): number {
  const { durationsMs, loop } = playback;
  if (durationsMs.length === 0) {
    throw new Error("durationsMs must contain at least one frame duration");
  }

  const cycleMs = durationsMs.reduce((sum, d) => sum + d, 0);
  let t = elapsedMs;
  if (loop) {
    t = ((t % cycleMs) + cycleMs) % cycleMs;
  } else if (t >= cycleMs) {
    return durationsMs.length - 1;
  }

  let cursor = 0;
  for (let i = 0; i < durationsMs.length; i += 1) {
    const duration = durationsMs[i]!;
    if (t < cursor + duration) {
      return i;
    }
    cursor += duration;
  }
  return durationsMs.length - 1;
}

/** Total length of one playback cycle (or the full one-shot). */
export function cycleDurationMs(playback: AnimationPlayback): number {
  if (playback.durationsMs.length === 0) {
    throw new Error("durationsMs must contain at least one frame duration");
  }
  return playback.durationsMs.reduce((sum, d) => sum + d, 0);
}

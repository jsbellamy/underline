/** Per-animation timing for the external dwarf pack — not in the hash-bound manifest.

Pack owns frame order; this module owns durations_ms and loop flags (#317).
Swing cycle length tracks Dig Rate: one Swing cycle = 1 / Dig Rate seconds (#319).
*/
import type { AnimationPlayback } from "../core/animation-player";

export type DwarfAnimationId = "idle" | "swing" | "walk";

export const SWING_FRAME_COUNT = 9;
export const WALK_FRAME_COUNT = 8;

/** Walk step between Faces — presentation-only; economy does not model walk delay. */
const WALK_CYCLE_MS = 400;

/** Idle hold while static; loop is irrelevant for a single frame but kept consistent. */
const IDLE_HOLD_MS = 1000;

function equalSlice(count: number, totalMs: number): number[] {
  const each = totalMs / count;
  const durations = Array.from({ length: count }, () => each);
  // Absorb float remainder on the last frame so cycleDurationMs === totalMs.
  const sum = durations.reduce((a, b) => a + b, 0);
  durations[count - 1] = each + (totalMs - sum);
  return durations;
}

export function dwarfPlayback(
  animation: DwarfAnimationId,
  digRate: number,
): AnimationPlayback {
  if (!(digRate > 0)) {
    throw new Error(`digRate must be positive, got ${digRate}`);
  }
  switch (animation) {
    case "idle":
      return { durationsMs: [IDLE_HOLD_MS], loop: true };
    case "swing":
      return {
        durationsMs: equalSlice(SWING_FRAME_COUNT, 1000 / digRate),
        loop: true,
      };
    case "walk":
      return {
        durationsMs: equalSlice(WALK_FRAME_COUNT, WALK_CYCLE_MS),
        loop: false,
      };
  }
}

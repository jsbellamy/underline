/** Dwarf animation state selection — engine-side, no DOM.

Rules (#314 / #321 / #364):
- `idle` when not mining and not hauling.
- `swing` while mining at the Face (not hauling).
- `walk` loops for a Haul leg — west on the out leg, east on the back leg.
*/
import { cycleDurationMs, frameAt } from "./animation-player";
import {
  dwarfPlayback,
  SWING_FRAME_COUNT,
  SWING_IMPACT_FRAME,
  type DwarfAnimationId,
} from "../data/dwarf-animation-timing";

export type DwarfAnimId = DwarfAnimationId;
export type DwarfFacing = "east" | "west";
export type HaulAnimPhase = "out" | "back";

export interface DwarfAnimController {
  readonly animation: DwarfAnimId;
  readonly facing: DwarfFacing;
  readonly digRate: number;
  startMining(nowMs: number): void;
  stopMining(nowMs: number): void;
  setHauling(phase: HaulAnimPhase | null, nowMs: number): void;
  setDigRate(digRate: number): void;
  /** Frame for `nowMs`; for `swing`, callers pass phase via frameIndexForSwingFraction. */
  frameIndexAt(nowMs: number): number;
  frameIndexForSwingFraction(fraction: number): number;
}

export interface DwarfAnimControllerOptions {
  digRate?: number;
  facing?: DwarfFacing;
}

export function createDwarfAnimController(
  options: DwarfAnimControllerOptions = {},
): DwarfAnimController {
  let digRate = options.digRate ?? 1;
  let facing: DwarfFacing = options.facing ?? "east";
  let animation: DwarfAnimId = "idle";
  let clipStartMs = 0;
  let mining = false;
  let haulingPhase: HaulAnimPhase | null = null;

  function playback() {
    return dwarfPlayback(animation, digRate);
  }

  function enter(next: DwarfAnimId, nowMs: number): void {
    if (animation === next) {
      return;
    }
    animation = next;
    clipStartMs = nowMs;
  }

  function applyHauling(phase: HaulAnimPhase | null, nowMs: number): void {
    haulingPhase = phase;
    if (phase === "out") {
      facing = "west";
      enter("walk", nowMs);
      return;
    }
    if (phase === "back") {
      facing = "east";
      enter("walk", nowMs);
      return;
    }
    enter(mining ? "swing" : "idle", nowMs);
    facing = "east";
  }

  const api: DwarfAnimController = {
    get animation() {
      return animation;
    },
    get facing() {
      return facing;
    },
    get digRate() {
      return digRate;
    },
    startMining(nowMs: number) {
      mining = true;
      if (haulingPhase === null) {
        enter("swing", nowMs);
      }
    },
    stopMining(nowMs: number) {
      mining = false;
      if (haulingPhase === null) {
        enter("idle", nowMs);
      }
    },
    setHauling(phase, nowMs: number) {
      if (phase === haulingPhase) {
        return;
      }
      applyHauling(phase, nowMs);
    },
    setDigRate(next: number) {
      if (!(next > 0)) {
        throw new Error(`digRate must be positive, got ${next}`);
      }
      digRate = next;
    },
    frameIndexAt(nowMs: number) {
      return frameAt(playback(), nowMs - clipStartMs);
    },
    frameIndexForSwingFraction(fraction: number) {
      const swingPlayback = dwarfPlayback("swing", digRate);
      const cycleMs = cycleDurationMs(swingPlayback);
      // Phase-shift so SWING_IMPACT_FRAME is shown when faceSwingProgress crosses an integer.
      const phase =
        ((((fraction + SWING_IMPACT_FRAME / SWING_FRAME_COUNT) % 1) + 1) % 1);
      const elapsedMs = phase * cycleMs;
      return frameAt(swingPlayback, elapsedMs);
    },
  };

  return api;
}

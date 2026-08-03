/** Dwarf animation state selection — engine-side, no DOM.

Rules (#314 / #321 / #364):
- `idle` when not mining and not hauling.
- `swing` while mining at the Face (not hauling).
- `walk` loops for a Haul leg — west on the out leg, east on the back leg.
*/
import { frameAt } from "./animation-player";
import {
  dwarfPlayback,
  type DwarfAnimationId,
} from "../data/dwarf-animation-timing";

export type DwarfAnimId = DwarfAnimationId;
export type DwarfFacing = "east" | "west";
export type HaulAnimPhase = "out" | "back";

export interface DwarfAnimController {
  readonly animation: DwarfAnimId;
  readonly facing: DwarfFacing;
  readonly frameIndex: number;
  readonly digRate: number;
  /** Milliseconds into the current clip (resets on animation change). */
  readonly clipElapsedMs: number;
  startMining(): void;
  stopMining(): void;
  setHauling(phase: HaulAnimPhase | null): void;
  advanceMs(dtMs: number): void;
  setDigRate(digRate: number): void;
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
  let clipElapsedMs = 0;
  let mining = false;
  let haulingPhase: HaulAnimPhase | null = null;

  function playback() {
    return dwarfPlayback(animation, digRate);
  }

  function enter(next: DwarfAnimId): void {
    if (animation === next) {
      return;
    }
    animation = next;
    clipElapsedMs = 0;
  }

  function applyHauling(phase: HaulAnimPhase | null): void {
    haulingPhase = phase;
    if (phase === "out") {
      facing = "west";
      enter("walk");
      return;
    }
    if (phase === "back") {
      facing = "east";
      enter("walk");
      return;
    }
    enter(mining ? "swing" : "idle");
    facing = "east";
  }

  const api: DwarfAnimController = {
    get animation() {
      return animation;
    },
    get facing() {
      return facing;
    },
    get frameIndex() {
      return frameAt(playback(), clipElapsedMs);
    },
    get digRate() {
      return digRate;
    },
    get clipElapsedMs() {
      return clipElapsedMs;
    },
    startMining() {
      mining = true;
      if (haulingPhase === null) {
        enter("swing");
      }
    },
    stopMining() {
      mining = false;
      if (haulingPhase === null) {
        enter("idle");
      }
    },
    setHauling(phase) {
      if (phase === haulingPhase) {
        return;
      }
      applyHauling(phase);
    },
    advanceMs(dtMs: number) {
      if (!(dtMs >= 0)) {
        throw new Error(`dtMs must be non-negative, got ${dtMs}`);
      }
      clipElapsedMs += dtMs;
    },
    setDigRate(next: number) {
      if (!(next > 0)) {
        throw new Error(`digRate must be positive, got ${next}`);
      }
      digRate = next;
      // Keep visual continuity: rescale elapsed so frame index stays put.
      const before = frameAt(playback(), clipElapsedMs);
      const nextPlayback = dwarfPlayback(animation, digRate);
      let cursor = 0;
      for (let i = 0; i < before; i += 1) {
        cursor += nextPlayback.durationsMs[i]!;
      }
      clipElapsedMs = cursor;
    },
  };

  return api;
}

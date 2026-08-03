/** Dwarf animation state selection — engine-side, no DOM.

Rules (#314 / #321):
- `idle` when not mining (and not finishing a walk).
- `swing` while mining at the Face.
- `walk` when a Mineable Block breaks and the Dwarf steps to the new Face;
  then resume `swing` (or `idle` if mining was stopped during the walk).
*/
import { cycleDurationMs, frameAt } from "./animation-player";
import {
  dwarfPlayback,
  type DwarfAnimationId,
} from "../data/dwarf-animation-timing";

export type DwarfAnimId = DwarfAnimationId;
export type DwarfFacing = "east" | "west";

export interface DwarfAnimController {
  readonly animation: DwarfAnimId;
  readonly facing: DwarfFacing;
  readonly frameIndex: number;
  readonly digRate: number;
  /** Milliseconds into the current clip (resets on animation change). */
  readonly clipElapsedMs: number;
  startMining(): void;
  stopMining(): void;
  faceBroken(): void;
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
  let resumeAfterWalk: "swing" | "idle" = "idle";

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
      if (animation !== "walk") {
        enter("swing");
      } else {
        resumeAfterWalk = "swing";
      }
    },
    stopMining() {
      mining = false;
      if (animation === "walk") {
        resumeAfterWalk = "idle";
        return;
      }
      enter("idle");
    },
    faceBroken() {
      resumeAfterWalk = mining ? "swing" : "idle";
      enter("walk");
    },
    advanceMs(dtMs: number) {
      if (!(dtMs >= 0)) {
        throw new Error(`dtMs must be non-negative, got ${dtMs}`);
      }
      clipElapsedMs += dtMs;
      if (animation === "walk") {
        const walk = playback();
        if (clipElapsedMs >= cycleDurationMs(walk)) {
          enter(resumeAfterWalk);
        }
      }
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

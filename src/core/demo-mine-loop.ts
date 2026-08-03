/** Presentation dig driver retained for anim-coupling unit coverage.

Prefer `createMinePresenter` + `createMiningSession` for the live Pane.
*/
import { cycleDurationMs } from "./animation-player";
import {
  createDwarfAnimController,
  type DwarfAnimController,
  type DwarfAnimId,
  type DwarfFacing,
} from "./dwarf-anim-state";
import { HARDNESS } from "./mining-engine";
import { dwarfPlayback } from "../data/dwarf-animation-timing";

export { HARDNESS };

export interface DemoMineSnapshot {
  animation: DwarfAnimId;
  facing: DwarfFacing;
  frameIndex: number;
  advance: number;
  /** Completed Swings on the current Face (`0…Hardness`). */
  faceSwingProgress: number;
  /** Fraction of the in-progress Swing (`0…1`) while swinging. */
  swingFraction: number;
  digRate: number;
}

export interface DemoMineLoop {
  snapshot(): DemoMineSnapshot;
  start(): void;
  stop(): void;
  advanceMs(dtMs: number): void;
  readonly anim: DwarfAnimController;
}

export interface DemoMineLoopOptions {
  digRate?: number;
  hardness?: number;
}

export function createDemoMineLoop(
  options: DemoMineLoopOptions = {},
): DemoMineLoop {
  const digRate = options.digRate ?? 1;
  const hardness = options.hardness ?? HARDNESS;
  const anim = createDwarfAnimController({ digRate });
  let advance = 0;
  let faceSwingProgress = 0;
  let swingCreditMs = 0;

  function swingCycleMs(): number {
    return cycleDurationMs(dwarfPlayback("swing", anim.digRate));
  }

  function snapshot(): DemoMineSnapshot {
    const cycle = swingCycleMs();
    const swingFraction =
      anim.animation === "swing" ? Math.min(1, swingCreditMs / cycle) : 0;
    return {
      animation: anim.animation,
      facing: anim.facing,
      frameIndex: anim.frameIndex,
      advance,
      faceSwingProgress,
      swingFraction,
      digRate: anim.digRate,
    };
  }

  function advanceMs(dtMs: number): void {
    if (!(dtMs >= 0)) {
      throw new Error(`dtMs must be non-negative, got ${dtMs}`);
    }
    let remaining = dtMs;
    while (remaining > 0) {
      if (anim.animation === "walk") {
        const walk = dwarfPlayback("walk", anim.digRate);
        const walkLeft = cycleDurationMs(walk) - anim.clipElapsedMs;
        const step = Math.min(remaining, Math.max(walkLeft, 0));
        anim.advanceMs(step);
        remaining -= step;
        continue;
      }

      if (anim.animation !== "swing") {
        anim.advanceMs(remaining);
        remaining = 0;
        continue;
      }

      const cycle = swingCycleMs();
      const untilSwing = cycle - swingCreditMs;
      const step = Math.min(remaining, untilSwing);
      anim.advanceMs(step);
      swingCreditMs += step;
      remaining -= step;

      if (swingCreditMs + 1e-9 >= cycle) {
        swingCreditMs = 0;
        faceSwingProgress += 1;
        if (faceSwingProgress >= hardness) {
          faceSwingProgress = 0;
          advance += 1;
          anim.faceBroken();
        }
      }
    }
  }

  return {
    anim,
    snapshot,
    start() {
      anim.startMining();
    },
    stop() {
      anim.stopMining();
    },
    advanceMs,
  };
}

/** Present the mining Tunnel from economy Snapshot + Dwarf anim. */

import {
  createDwarfAnimController,
  type DwarfAnimController,
} from "../core/dwarf-anim-state";
import type { DemoMineSnapshot } from "../core/demo-mine-loop";
import { digRateFor } from "../core/mining-engine";
import type { MiningSession } from "../core/mining-session";

export interface MinePresenter {
  snapshot(): DemoMineSnapshot;
  start(): void;
  advanceMs(dtMs: number): void;
  syncDigRate(): void;
  readonly anim: DwarfAnimController;
}

export function createMinePresenter(session: MiningSession): MinePresenter {
  const anim = createDwarfAnimController({
    digRate: digRateFor(session.snapshot.digRateUpgradeCount),
  });

  function snapshot(): DemoMineSnapshot {
    const snap = session.snapshot;
    const whole = Math.floor(snap.faceSwingProgress);
    const frac = snap.faceSwingProgress - whole;
    return {
      animation: anim.animation,
      facing: anim.facing,
      frameIndex: anim.frameIndex,
      advance: snap.advance,
      faceSwingProgress: whole,
      swingFraction: anim.animation === "swing" ? frac : 0,
      digRate: anim.digRate,
    };
  }

  return {
    anim,
    snapshot,
    start() {
      anim.startMining();
    },
    syncDigRate() {
      anim.setDigRate(digRateFor(session.snapshot.digRateUpgradeCount));
    },
    advanceMs(dtMs: number) {
      const before = session.snapshot.advance;
      session.advanceLive(dtMs);
      const gained = session.snapshot.advance - before;
      for (let i = 0; i < gained; i += 1) {
        anim.faceBroken();
      }
      anim.advanceMs(dtMs);
    },
  };
}

/** Present the mining Tunnel from economy Snapshot + Dwarf anim. */

import {
  createDwarfAnimController,
  type DwarfAnimController,
  type DwarfAnimId,
  type DwarfFacing,
} from "../core/dwarf-anim-state";
import { digRateFor } from "../core/mining-engine";
import type { MiningSession } from "../core/mining-session";
import type { SaveStore } from "../core/mining-save";
import { loadSettings } from "../core/settings-save";
import {
  createMiningAudio,
  type MiningAudio,
} from "./mining-audio";

export interface TunnelSnapshot {
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

export interface MinePresenter {
  snapshot(): TunnelSnapshot;
  start(): void;
  advanceMs(dtMs: number): void;
  syncDigRate(): void;
  setSoundEnabled(enabled: boolean): void;
  readonly anim: DwarfAnimController;
}

export interface MinePresenterOptions {
  audio?: MiningAudio;
  store?: SaveStore;
  createAudioContext?: () => AudioContext;
}

export function createMinePresenter(
  session: MiningSession,
  options: MinePresenterOptions = {},
): MinePresenter {
  const anim = createDwarfAnimController({
    digRate: digRateFor(session.snapshot.digRateUpgradeCount),
  });

  const audio =
    options.audio ??
    (options.createAudioContext
      ? createMiningAudio({ createAudioContext: options.createAudioContext })
      : null);

  if (audio && !options.audio && options.store) {
    if (loadSettings(options.store).soundEnabled) {
      audio.setEnabled(true);
    }
  }

  let swingCycleRemainderMs = 0;

  function swingCycleMs(): number {
    return 1000 / anim.digRate;
  }

  function snapshot(): TunnelSnapshot {
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
    setSoundEnabled(enabled: boolean) {
      audio?.setEnabled(enabled);
    },
    advanceMs(dtMs: number) {
      const before = session.snapshot.advance;
      session.advanceLive(dtMs);
      const gained = session.snapshot.advance - before;
      if (audio && gained > 0) {
        audio.faceBroken(gained);
      }
      for (let i = 0; i < gained; i += 1) {
        anim.faceBroken();
      }

      const cycleMs = swingCycleMs();
      swingCycleRemainderMs += dtMs;
      const completed = Math.floor(swingCycleRemainderMs / cycleMs);
      swingCycleRemainderMs -= completed * cycleMs;
      if (audio && completed > 0) {
        audio.swing(completed);
      }

      anim.advanceMs(dtMs);
    },
  };
}

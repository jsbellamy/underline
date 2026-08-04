/** Present the mining Tunnel from economy Snapshot + Dwarf anim. */

import {
  createDwarfAnimController,
  type DwarfAnimController,
  type DwarfAnimId,
  type DwarfFacing,
  type HaulAnimPhase,
} from "../core/dwarf-anim-state";
import { digRateFor, HAUL_ROUND_TRIP_MS } from "../core/mining-engine";
import type { MiningSession } from "../core/mining-session";
import type { SaveStore } from "../core/mining-save";
import { loadSettings } from "../core/settings-save";
import {
  createMiningAudio,
  type MiningAudio,
} from "./mining-audio";

export type TunnelHaulPhase = "none" | HaulAnimPhase;

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
  haulPhase: TunnelHaulPhase;
  /** `0` at Haul start, rising to `1` at round-trip end; `0` when not hauling. */
  haulProgress: number;
  /** Face slide-in progress (`0` at Advance bump, `1` when settled). */
  faceSlide: number;
}

export const FACE_SLIDE_MS = 400;

export interface MinePresenter {
  snapshot(nowMs?: number): TunnelSnapshot;
  start(): void;
  advanceMs(dtMs: number): void;
  syncDigRate(): void;
  setSoundEnabled(enabled: boolean): void;
  readonly simNowMs: number;
  readonly anim: DwarfAnimController;
}

export interface MinePresenterOptions {
  audio?: MiningAudio;
  store?: SaveStore;
  createAudioContext?: () => AudioContext;
}

function haulAnimPhase(haulRemainingMs: number): HaulAnimPhase | null {
  if (haulRemainingMs === 0) {
    return null;
  }
  if (haulRemainingMs > HAUL_ROUND_TRIP_MS / 2) {
    return "out";
  }
  return "back";
}

function haulProgress(haulRemainingMs: number): number {
  if (haulRemainingMs === 0) {
    return 0;
  }
  return 1 - haulRemainingMs / HAUL_ROUND_TRIP_MS;
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
  let faceSlide = 1;
  let faceSlideElapsedMs = 0;
  let lastAdvance = session.snapshot.advance;
  let simNowMs = 0;
  let faceSwingProgressAtTick = session.snapshot.faceSwingProgress;

  function swingCycleMs(): number {
    return 1000 / anim.digRate;
  }

  function syncHaulAnim(): void {
    anim.setHauling(haulAnimPhase(session.snapshot.haulRemainingMs), simNowMs);
  }

  function swingFractionAt(nowMs: number, hauling: boolean): number {
    if (hauling) {
      return faceSwingProgressAtTick - Math.floor(faceSwingProgressAtTick);
    }
    const progress =
      faceSwingProgressAtTick + anim.digRate * (nowMs - simNowMs) / 1000;
    return progress - Math.floor(progress);
  }

  function snapshot(nowMs: number = simNowMs): TunnelSnapshot {
    const snap = session.snapshot;
    const whole = Math.floor(snap.faceSwingProgress);
    const remaining = snap.haulRemainingMs;
    const phase = haulAnimPhase(remaining);
    const hauling = remaining > 0;

    let swingFraction = 0;
    let frameIndex: number;

    if (anim.animation === "swing") {
      swingFraction = swingFractionAt(nowMs, hauling);
      frameIndex = anim.frameIndexForSwingFraction(swingFraction);
    } else {
      frameIndex = anim.frameIndexAt(nowMs);
    }

    return {
      animation: anim.animation,
      facing: anim.facing,
      frameIndex,
      advance: snap.advance,
      faceSwingProgress: whole,
      swingFraction,
      digRate: anim.digRate,
      haulPhase: phase ?? "none",
      haulProgress: haulProgress(remaining),
      faceSlide,
    };
  }

  return {
    anim,
    get simNowMs() {
      return simNowMs;
    },
    snapshot,
    start() {
      anim.startMining(simNowMs);
    },
    syncDigRate() {
      anim.setDigRate(digRateFor(session.snapshot.digRateUpgradeCount));
    },
    setSoundEnabled(enabled: boolean) {
      audio?.setEnabled(enabled);
    },
    advanceMs(dtMs: number) {
      simNowMs += dtMs;
      const before = session.snapshot.advance;
      const haulingBefore = session.snapshot.haulRemainingMs > 0;
      session.advanceLive(dtMs);
      const gained = session.snapshot.advance - before;
      if (audio && gained > 0) {
        audio.faceBroken(gained);
      }

      faceSwingProgressAtTick = session.snapshot.faceSwingProgress;

      if (session.snapshot.advance > lastAdvance) {
        faceSlide = 0;
        faceSlideElapsedMs = 0;
        lastAdvance = session.snapshot.advance;
      }
      if (faceSlide < 1) {
        faceSlideElapsedMs += dtMs;
        faceSlide = Math.min(1, faceSlideElapsedMs / FACE_SLIDE_MS);
      }

      syncHaulAnim();

      const haulingAfter = session.snapshot.haulRemainingMs > 0;
      if (!haulingBefore && !haulingAfter) {
        const cycleMs = swingCycleMs();
        swingCycleRemainderMs += dtMs;
        const completed = Math.floor(swingCycleRemainderMs / cycleMs);
        swingCycleRemainderMs -= completed * cycleMs;
        if (audio && completed > 0) {
          audio.swing(completed);
        }
      } else if (!haulingAfter) {
        swingCycleRemainderMs = 0;
      }
    },
  };
}

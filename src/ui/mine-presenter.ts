/** Present the mining Tunnel from economy Snapshot + Dwarf anim. */

import {
  createDwarfAnimController,
  type DwarfAnimController,
  type DwarfAnimId,
  type DwarfFacing,
  type HaulAnimPhase,
} from "../core/dwarf-anim-state";
import { createHeapPileSim, type HeapPileSim } from "../core/heap-pile-sim";
import {
  digRateFor,
  HAUL_ROUND_TRIP_MS,
  heapCapacityFor,
  pickDamageFor,
  pickupMsPerLoad,
} from "../core/mining-engine";
import type { MiningSession } from "../core/mining-session";
import type { SaveStore } from "../core/mining-save";
import { loadSettings } from "../core/settings-save";
import {
  HEAP_ORE_VARIANT_COUNT,
  heapOreContentCenter,
  heapOreRadius,
} from "./heap-ore-variants";
import {
  createMiningAudio,
  type MiningAudio,
} from "./mining-audio";
import {
  HAULER_GRAB_X,
  HEAP_BIN_CEILING_Y,
  HEAP_BIN_EAST_X,
  HEAP_BIN_FLOOR_Y,
  HEAP_BIN_WEST_X,
  HEAP_GRAB_REACH_PX,
  HEAP_PILE_SEED,
  HEAP_RENDER_CEILING,
  HEAP_SPAWN_X,
  ORE_FALL_MS,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";

export type TunnelHaulPhase = "none" | HaulAnimPhase;
export type HaulerPhase = "pickup" | HaulAnimPhase;

export interface HaulerSnapshot {
  animation: DwarfAnimId;
  facing: DwarfFacing;
  frameIndex: number;
  /** "pickup" while lifting a Load at the Face, else the travel phase. */
  phase: HaulerPhase;
  /** 0 at Haul start, 1 at round-trip end; 0 while picking up. */
  haulProgress: number;
  /** Fraction of the current Load's pickup, 0…1; 0 while travelling. */
  pickupProgress: number;
}

export interface HeapOreSnapshot {
  id: number;
  left: number;
  bottom: number;
  variantIndex: number;
}

export interface TunnelSnapshot {
  animation: DwarfAnimId;
  facing: DwarfFacing;
  frameIndex: number;
  advance: number;
  /** Completed Swings on the current Face (`0…Hardness`). */
  faceSwingProgress: number;
  /** Fraction of the in-progress Swing (`0…1`) while swinging. */
  swingFraction: number;
  /** Pick Damage per Swing for the current Crew. */
  pickDamage: number;
  digRate: number;
  haulPhase: TunnelHaulPhase;
  /** `0` at Haul start, rising to `1` at round-trip end; `0` when not hauling. */
  haulProgress: number;
  /** Face slide-in progress (`0` at Advance bump, `1` when settled). */
  faceSlide: number;
  /** Absent when the Crew is one Dwarf. */
  hauler?: HaulerSnapshot;
  crewSize: number;
  heapLoads: number;
  /** Settled Heap Ore bodies, ascending by `id`; empty for a one-Dwarf Crew. */
  heapOre: readonly HeapOreSnapshot[];
  /** Variant of the Load in the Hauler's hands; absent when nothing is carried. */
  carriedVariantIndex?: number;
  /** Ore still falling toward the Bag; empty when nothing is in flight. */
  fallingOre: readonly { slot: number; progress: number }[];
}

export const FACE_SLIDE_MS = 400;

export interface MinePresenter {
  snapshot(nowMs?: number): TunnelSnapshot;
  start(): void;
  advanceMs(dtMs: number): void;
  releaseAudioDueTo(nowMs: number): void;
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

function haulerPhase(haulRemainingMs: number): HaulerPhase {
  if (haulRemainingMs > 0) {
    return haulAnimPhase(haulRemainingMs) ?? "pickup";
  }
  return "pickup";
}

function pickupProgressFraction(
  haulRemainingMs: number,
  pickupProgressMs: number,
  haulSpeedUpgradeCount: number,
): number {
  if (haulRemainingMs > 0) {
    return 0;
  }
  const pickupMs = pickupMsPerLoad(haulSpeedUpgradeCount);
  return Math.min(1, Math.max(0, pickupProgressMs / pickupMs));
}

function isPickupLifted(
  haulRemainingMs: number,
  heapLoads: number,
  pickupProgressMs: number,
  haulSpeedUpgradeCount: number,
): boolean {
  return (
    haulRemainingMs === 0 &&
    heapLoads >= 1 &&
    pickupProgressFraction(
      haulRemainingMs,
      pickupProgressMs,
      haulSpeedUpgradeCount,
    ) > 0.5
  );
}

function frameIndexFor(
  ctrl: DwarfAnimController,
  nowMs: number,
  swingFraction: number,
): number {
  if (ctrl.animation === "swing") {
    return ctrl.frameIndexForSwingFraction(swingFraction);
  }
  return ctrl.frameIndexAt(nowMs);
}

export function createMinePresenter(
  session: MiningSession,
  options: MinePresenterOptions = {},
): MinePresenter {
  const miner = createDwarfAnimController({
    digRate: digRateFor(session.snapshot.digRateUpgradeCount),
  });
  const hauler = createDwarfAnimController({
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

  let faceSlide = 1;
  let faceSlideElapsedMs = 0;
  let lastAdvance = session.snapshot.advance;
  let simNowMs = 0;
  let faceSwingProgressAtTick = session.snapshot.faceSwingProgress;
  const activeFalls: number[] = [];

  const pile: HeapPileSim = createHeapPileSim({
    bin: {
      floorY: HEAP_BIN_FLOOR_Y,
      westX: HEAP_BIN_WEST_X,
      eastX: HEAP_BIN_EAST_X,
      ceilingY: HEAP_BIN_CEILING_Y,
    },
    seed: HEAP_PILE_SEED,
  });
  let spawnCount = 0;
  const variantByBodyId = new Map<number, number>();
  let carriedVariantIndex: number | undefined;

  function pileTargetCount(): number {
    const snap = session.snapshot;
    if (snap.crewSize !== 2) {
      return 0;
    }
    const lifted = isPickupLifted(
      snap.haulRemainingMs,
      snap.heapLoads,
      snap.pickupProgressMs,
      snap.haulSpeedUpgradeCount,
    )
      ? 1
      : 0;
    return Math.min(
      Math.max(0, snap.heapLoads - lifted),
      HEAP_RENDER_CEILING,
    );
  }

  function spawnPileBody(): void {
    const v = spawnCount % HEAP_ORE_VARIANT_COUNT;
    spawnCount += 1;
    const id = pile.spawnJittered(
      heapOreRadius(v),
      HEAP_SPAWN_X,
      ORE_SPAWN_BOTTOM,
    );
    variantByBodyId.set(id, v);
  }

  function reconcilePile(nowMs: number): void {
    const snap = session.snapshot;
    const target = pileTargetCount();
    const count = pile.bodies.length;
    const lifted = isPickupLifted(
      snap.haulRemainingMs,
      snap.heapLoads,
      snap.pickupProgressMs,
      snap.haulSpeedUpgradeCount,
    );

    if (target > count) {
      const toSpawn = target - count;
      for (let i = 0; i < toSpawn; i += 1) {
        spawnPileBody();
      }
      if (toSpawn > 1) {
        pile.settle();
      }
    } else if (target < count) {
      const toRemove = count - target;
      for (let i = 0; i < toRemove; i += 1) {
        const removedId = pile.removeGrabbed(HAULER_GRAB_X, HEAP_GRAB_REACH_PX);
        if (removedId !== null) {
          carriedVariantIndex = variantByBodyId.get(removedId);
          variantByBodyId.delete(removedId);
        }
      }
    }

    if (!lifted) {
      carriedVariantIndex = undefined;
    } else if (carriedVariantIndex === undefined) {
      carriedVariantIndex = spawnCount % HEAP_ORE_VARIANT_COUNT;
    }

    pile.stepTo(Math.max(pile.nowMs, nowMs));
  }

  function projectHeapOre(): readonly HeapOreSnapshot[] {
    return pile.bodies.map((body) => {
      const v = variantByBodyId.get(body.id)!;
      const { cx, cyFromBottom } = heapOreContentCenter(v);
      return {
        id: body.id,
        left: Math.round(body.x - cx),
        bottom: Math.round(body.y - cyFromBottom),
        variantIndex: v,
      };
    });
  }

  const initialTarget = pileTargetCount();
  for (let i = 0; i < initialTarget; i += 1) {
    spawnPileBody();
  }
  if (initialTarget > 0) {
    pile.settle();
  }

  function cleanFalls(nowMs: number): void {
    if (isTwoDwarf()) {
      return;
    }
    for (let i = activeFalls.length - 1; i >= 0; i -= 1) {
      const progress = (nowMs - activeFalls[i]!) / ORE_FALL_MS;
      if (progress >= 1) {
        activeFalls.splice(i, 1);
      }
    }
  }

  function projectFallingOre(
    nowMs: number,
  ): readonly { slot: number; progress: number }[] {
    if (isTwoDwarf()) {
      return [];
    }
    const result: { slot: number; progress: number }[] = [];
    for (let i = 0; i < activeFalls.length; i += 1) {
      const spawnSimMs = activeFalls[i]!;
      const progress = Math.min(
        1,
        Math.max(0, (nowMs - spawnSimMs) / ORE_FALL_MS),
      );
      if (progress >= 1) {
        continue;
      }
      result.push({ slot: i, progress });
    }
    return result;
  }

  function isTwoDwarf(): boolean {
    return session.snapshot.crewSize === 2;
  }

  function syncMinerAnim(): void {
    if (isTwoDwarf()) {
      miner.setHauling(null, simNowMs);
      const cap = heapCapacityFor(session.snapshot.carryCapacityUpgradeCount);
      if (session.snapshot.heapLoads >= cap) {
        miner.stopMining(simNowMs);
      } else {
        miner.startMining(simNowMs);
      }
      return;
    }
    miner.setHauling(
      haulAnimPhase(session.snapshot.haulRemainingMs),
      simNowMs,
    );
  }

  function syncHaulerAnim(): void {
    if (!isTwoDwarf()) {
      return;
    }
    const snap = session.snapshot;
    if (snap.haulRemainingMs > 0) {
      hauler.setHauling(haulAnimPhase(snap.haulRemainingMs), simNowMs);
      return;
    }
    if (snap.heapLoads === 0) {
      hauler.setHauling(null, simNowMs);
      return;
    }
    const progress = pickupProgressFraction(
      snap.haulRemainingMs,
      snap.pickupProgressMs,
      snap.haulSpeedUpgradeCount,
    );
    hauler.setHauling(progress <= 0.5 ? "back" : "out", simNowMs);
  }

  function syncHaulAnim(): void {
    syncMinerAnim();
    syncHaulerAnim();
  }

  function swingFractionAt(nowMs: number, hauling: boolean): number {
    const pickDamage = pickDamageFor(session.snapshot.pickDamageUpgradeCount);
    const swingsAtTick = faceSwingProgressAtTick / pickDamage;
    if (hauling) {
      return swingsAtTick - Math.floor(swingsAtTick);
    }
    const swings =
      swingsAtTick + miner.digRate * (nowMs - simNowMs) / 1000;
    const clamped = Math.max(0, swings);
    return clamped - Math.floor(clamped);
  }

  function buildHaulerSnapshot(nowMs: number): HaulerSnapshot | undefined {
    if (!isTwoDwarf()) {
      return undefined;
    }
    const snap = session.snapshot;
    const remaining = snap.haulRemainingMs;
    const phase = haulerPhase(remaining);
    const travelling = remaining > 0;
    const swingFrac = swingFractionAt(nowMs, travelling);

    return {
      animation: hauler.animation,
      facing: hauler.facing,
      frameIndex: frameIndexFor(hauler, nowMs, swingFrac),
      phase,
      haulProgress: travelling ? haulProgress(remaining) : 0,
      pickupProgress: pickupProgressFraction(
        remaining,
        snap.pickupProgressMs,
        snap.haulSpeedUpgradeCount,
      ),
    };
  }

  function snapshot(nowMs: number = simNowMs): TunnelSnapshot {
    reconcilePile(nowMs);
    cleanFalls(nowMs);
    const snap = session.snapshot;
    const pickDamage = pickDamageFor(snap.pickDamageUpgradeCount);
    const whole = Math.floor(snap.faceSwingProgress / pickDamage);
    const remaining = snap.haulRemainingMs;
    const twoDwarf = isTwoDwarf();
    const phase = twoDwarf ? null : haulAnimPhase(remaining);
    const hauling = twoDwarf ? false : remaining > 0;

    let swingFraction = 0;
    let frameIndex: number;

    if (miner.animation === "swing") {
      swingFraction = swingFractionAt(nowMs, hauling);
      frameIndex = miner.frameIndexForSwingFraction(swingFraction);
    } else {
      frameIndex = miner.frameIndexAt(nowMs);
    }

    const haulerSnap = buildHaulerSnapshot(nowMs);

    return {
      animation: miner.animation,
      facing: miner.facing,
      frameIndex,
      advance: snap.advance,
      faceSwingProgress: whole,
      swingFraction,
      pickDamage,
      digRate: miner.digRate,
      haulPhase: phase ?? "none",
      haulProgress: twoDwarf ? 0 : haulProgress(remaining),
      faceSlide,
      ...(haulerSnap !== undefined ? { hauler: haulerSnap } : {}),
      crewSize: snap.crewSize,
      heapLoads: snap.heapLoads,
      heapOre: projectHeapOre(),
      ...(carriedVariantIndex !== undefined
        ? { carriedVariantIndex }
        : {}),
      fallingOre: projectFallingOre(nowMs),
    };
  }

  return {
    anim: miner,
    get simNowMs() {
      return simNowMs;
    },
    snapshot,
    start() {
      if (isTwoDwarf()) {
        syncMinerAnim();
        syncHaulerAnim();
      } else {
        miner.startMining(simNowMs);
      }
    },
    syncDigRate() {
      const rate = digRateFor(session.snapshot.digRateUpgradeCount);
      miner.setDigRate(rate);
      hauler.setDigRate(rate);
    },
    setSoundEnabled(enabled: boolean) {
      audio?.setEnabled(enabled);
    },
    releaseAudioDueTo(nowMs: number) {
      audio?.releaseDueTo(nowMs);
    },
    advanceMs(dtMs: number) {
      const windowStartSimMs = simNowMs;
      simNowMs += dtMs;
      const { events } = session.advanceLive(dtMs);
      if (audio) {
        audio.handleEvents(events, windowStartSimMs, dtMs);
      }

      for (const event of events) {
        if (event.type === "loadDropped" && !isTwoDwarf()) {
          activeFalls.unshift(windowStartSimMs + event.atMs);
        }
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
    },
  };
}

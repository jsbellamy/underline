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
  haulRoundTripMsFor,
  pickDamageFor,
} from "../core/mining-engine";
import { tripPhaseFor } from "../core/trip-phase";
import type { MiningSession } from "../core/mining-session";
import type { SaveStore } from "../core/mining-save";
import { loadSettings } from "../core/settings-save";
import {
  HEAP_ORE_VARIANT_COUNT,
  heapOreArtKey,
  heapOreContentCenter,
  heapOreRadius,
} from "./heap-ore-variants";
import {
  createMiningAudio,
  type MiningAudio,
} from "./mining-audio";
import {
  HEAP_BIN_CEILING_Y,
  HEAP_BIN_EAST_X,
  HEAP_BIN_FLOOR_Y,
  HEAP_BIN_WEST_X,
  HEAP_PILE_SEED,
  HEAP_RENDER_CEILING,
  HEAP_SPAWN_X,
  DWARF_FRAME_W,
  DWARF_SCALE,
  FLOOR_Y,
  HAULER_HAND_DX,
  HAULER_HAND_DY,
  MINING_MARK_X,
  ORE_FALL_MS,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";
import {
  createHaulerChoreography,
  pickupProgressFraction,
  type HaulerChoreography,
  type HaulerChoreographyPresenterSeam,
  type HaulerPhase,
  type HeapBody,
} from "./hauler-choreography";
import { tripLeftFor } from "./trip-position";
import { tunnelArtContentBottomGap } from "../data/tunnel-art-pack";
import { TUNNEL_ART_PACK } from "./tunnel-art";

export type TunnelHaulPhase = "none" | HaulAnimPhase | "unload";
export type { HaulerPhase };
export { tripLeftFor };

export interface HaulerSnapshot {
  animation: DwarfAnimId;
  facing: DwarfFacing;
  frameIndex: number;
  /** Sprite left in Pane px during pickup; travel arc ignores this. */
  left: number;
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

export interface CarriedOreSnapshot {
  readonly left: number;
  readonly bottom: number;
  readonly variantIndex: number;
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
  /** Loads in the Hauler's hands, ascending by pickup order; empty when none. */
  readonly carriedOre: readonly CarriedOreSnapshot[];
  /** Ore still falling toward the Bag; empty when nothing is in flight. */
  fallingOre: readonly { slot: number; progress: number }[];
  /** Miner sprite left in Pane px — presenter-owned horizontal position. */
  minerLeft: number;
  /** Remaining Haul countdown mirrored from the engine snapshot. */
  haulRemainingMs: number;
}

export const FACE_SLIDE_MS = 400;
export const SPILL_LIFETIME_MS = 900;

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

export function createMinePresenter(
  session: MiningSession,
  options: MinePresenterOptions = {},
): MinePresenter {
  const miner = createDwarfAnimController({
    digRate: digRateFor(session.snapshot.digRateUpgradeCount),
  });
  const haulerChoreography: HaulerChoreography & HaulerChoreographyPresenterSeam =
    createHaulerChoreography({
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
  const spillExpiryByBodyId = new Map<number, number>();
  let carriedVariantIndexes: number[] = [];

  function minerLeftFor(_nowMs: number): number {
    const snap = session.snapshot;
    if (faceSlide < 1 || isTwoDwarf()) {
      return MINING_MARK_X;
    }
    if (snap.haulRemainingMs > 0) {
      return tripLeftFor(
        snap.haulRemainingMs,
        MINING_MARK_X,
        snap.unloadSpeedUpgradeCount,
      );
    }
    return MINING_MARK_X;
  }

  function pileTargetCount(liftedLoadCount: number): number {
    const snap = session.snapshot;
    if (snap.crewSize !== 2) {
      return 0;
    }
    return Math.min(
      Math.max(0, snap.heapLoads - liftedLoadCount),
      HEAP_RENDER_CEILING,
    );
  }

  function heapBodiesForChoreography(): readonly HeapBody[] {
    const excluded = spillBodyIds();
    return pile.bodies
      .filter((b) => !excluded.has(b.id))
      .map((b) => ({ id: b.id, x: b.x, y: b.y }));
  }

  function spawnPileBody(): number {
    const v = spawnCount % HEAP_ORE_VARIANT_COUNT;
    spawnCount += 1;
    const id = pile.spawnJittered(
      heapOreRadius(v),
      HEAP_SPAWN_X,
      ORE_SPAWN_BOTTOM,
    );
    variantByBodyId.set(id, v);
    return id;
  }

  function spillBodyIds(): ReadonlySet<number> {
    return new Set(spillExpiryByBodyId.keys());
  }

  function expireSpillBodies(nowMs: number): void {
    for (const [id, expiryMs] of [...spillExpiryByBodyId.entries()]) {
      if (expiryMs <= nowMs) {
        pile.remove(id);
        spillExpiryByBodyId.delete(id);
        variantByBodyId.delete(id);
      }
    }
  }

  function applyLiftResult(
    lift: { liftedIds: readonly number[]; carrying: boolean },
    excluded: ReadonlySet<number>,
    liftedLoadCount: number,
  ): void {
    if (!lift.carrying) {
      carriedVariantIndexes = [];
      return;
    }

    const target = pileTargetCount(liftedLoadCount);
    const count = pile.bodies.filter((b) => !excluded.has(b.id)).length;

    if (lift.liftedIds.length === 0) {
      return;
    }

    if (!(count > target)) {
      if (carriedVariantIndexes.length === 0) {
        const variant = variantByBodyId.get(lift.liftedIds[0]!);
        if (variant !== undefined) {
          carriedVariantIndexes = [variant];
        }
      }
      return;
    }

    for (const bodyId of lift.liftedIds) {
      if (!pile.remove(bodyId)) {
        continue;
      }
      const variant = variantByBodyId.get(bodyId);
      if (variant !== undefined) {
        carriedVariantIndexes.push(variant);
        variantByBodyId.delete(bodyId);
      }
    }
  }

  function reconcilePile(nowMs: number): void {
    expireSpillBodies(nowMs);

    const snap = session.snapshot;
    const excluded = spillBodyIds();

    let lift = {
      liftedIds: [] as readonly number[],
      carrying: false,
    };
    if (isTwoDwarf()) {
      lift = haulerChoreography.advanceTo(
        snap,
        nowMs,
        heapBodiesForChoreography(),
      );
    }

    const liftedLoadCount = isTwoDwarf()
      ? haulerChoreography.liftedLoadCountForPile(snap)
      : 0;
    const target = pileTargetCount(liftedLoadCount);
    const count = pile.bodies.filter((b) => !excluded.has(b.id)).length;

    if (target > count) {
      const toSpawn = target - count;
      for (let i = 0; i < toSpawn; i += 1) {
        spawnPileBody();
      }
      if (toSpawn > 1) {
        pile.settle();
      }
    }

    applyLiftResult(lift, excluded, liftedLoadCount);

    pile.stepTo(Math.max(pile.nowMs, nowMs));
  }

  function adjustedCarriedOreBottom(
    slotBottom: number,
    variantIndex: number,
  ): number {
    const artKey = heapOreArtKey(variantIndex);
    return (
      slotBottom -
      tunnelArtContentBottomGap(TUNNEL_ART_PACK, artKey, ORE_SIZE)
    );
  }

  function projectCarriedOre(
    hauler: HaulerSnapshot | undefined,
  ): readonly CarriedOreSnapshot[] {
    if (!hauler || carriedVariantIndexes.length === 0) {
      return [];
    }
    const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
    const handDx =
      hauler.facing === "west"
        ? dwarfW - ORE_SIZE - HAULER_HAND_DX
        : HAULER_HAND_DX;
    const slotBottom = FLOOR_Y + HAULER_HAND_DY;
    return carriedVariantIndexes.map((variantIndex) => ({
      left: hauler.left + handDx,
      bottom: adjustedCarriedOreBottom(slotBottom, variantIndex),
      variantIndex,
    }));
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

  const initialTarget = pileTargetCount(0);
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
      // ADR 0016: a full Heap Spills rather than stalling the Miner, so he keeps
      // Swinging — the engine keeps emitting `swing`, and the sprite must agree.
      miner.setHauling(null, simNowMs);
      miner.startMining(simNowMs);
      return;
    }
    const leg = tripPhaseFor(session.snapshot)?.leg;
    if (leg === "unload") {
      miner.stopMining(simNowMs);
      miner.setHauling(null, simNowMs);
      return;
    }
    if (leg === "out" || leg === "back") {
      miner.setHauling(leg, simNowMs);
      return;
    }
    miner.startMining(simNowMs);
    miner.setHauling(null, simNowMs);
  }

  function syncHaulAnim(): void {
    syncMinerAnim();
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
    const remaining =
      snap.haulRemainingMs > 0
        ? Math.min(
            haulRoundTripMsFor(snap.unloadSpeedUpgradeCount),
            snap.haulRemainingMs + Math.max(0, simNowMs - nowMs),
          )
        : 0;
    const tripPhase = tripPhaseFor({ ...snap, haulRemainingMs: remaining });
    const travelling = remaining > 0;
    const swingFrac = swingFractionAt(nowMs, travelling);
    const stance = haulerChoreography.stanceAt(
      { ...snap, haulRemainingMs: remaining },
      nowMs,
    );
    const frameIndex =
      stance.animation === "idle" &&
      (stance.phase === "out" || stance.phase === "unload")
        ? 0
        : haulerChoreography.frameIndexAt(nowMs, swingFrac);

    return {
      animation: stance.animation,
      facing: stance.facing,
      frameIndex,
      left: stance.left,
      phase: stance.phase,
      haulProgress: travelling ? (tripPhase?.tripProgress ?? 0) : 0,
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
    const tripPhase = twoDwarf
      ? null
      : tripPhaseFor({ ...snap, haulRemainingMs: remaining });
    const phase = tripPhase?.leg ?? null;
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
      haulPhase:
        phase === null
          ? "none"
          : phase === "unload"
            ? "unload"
            : phase,
      haulProgress: twoDwarf ? 0 : (tripPhase?.tripProgress ?? 0),
      faceSlide,
      ...(haulerSnap !== undefined ? { hauler: haulerSnap } : {}),
      crewSize: snap.crewSize,
      heapLoads: snap.heapLoads,
      heapOre: projectHeapOre(),
      carriedOre: projectCarriedOre(haulerSnap),
      fallingOre: projectFallingOre(nowMs),
      minerLeft: minerLeftFor(nowMs),
      haulRemainingMs: remaining,
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
        reconcilePile(simNowMs);
      } else {
        miner.startMining(simNowMs);
      }
    },
    syncDigRate() {
      const rate = digRateFor(session.snapshot.digRateUpgradeCount);
      miner.setDigRate(rate);
      haulerChoreography.setDigRate(rate);
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
        if (
          event.type === "loadSpilled" &&
          isTwoDwarf() &&
          spillExpiryByBodyId.size === 0
        ) {
          const spawnNowMs = windowStartSimMs + event.atMs;
          const id = spawnPileBody();
          spillExpiryByBodyId.set(id, spawnNowMs + SPILL_LIFETIME_MS);
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

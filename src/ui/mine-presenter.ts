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
  grabSizeFor,
  HAUL_TRAVEL_MS,
  haulRoundTripMsFor,
  initialSnapshot,
  pickDamageFor,
  pickupMsPerLoad,
  unloadMsFor,
} from "../core/mining-engine";
import { tripPhaseFor } from "../core/trip-phase";
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
  CART_MARK_X,
  FLOOR_Y,
  HAULER_HAND_DX,
  HAULER_HAND_DY,
  HAULER_MARK_X,
  HAULER_WALK_PX_PER_MS,
  haulerStationFor,
  HEAP_BIN_CEILING_Y,
  HEAP_BIN_EAST_X,
  HEAP_BIN_FLOOR_Y,
  HEAP_BIN_WEST_X,
  HEAP_PILE_SEED,
  HEAP_RENDER_CEILING,
  HEAP_SPAWN_X,
  MINING_MARK_X,
  ORE_FALL_MS,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";

export type TunnelHaulPhase = "none" | HaulAnimPhase | "unload";
export type HaulerPhase = "pickup" | "unload" | HaulAnimPhase;

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
  /** Variants of Loads in the Hauler's hands, ascending by pickup order. */
  carriedVariantIndexes?: readonly number[];
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

export function tripLeftFor(
  haulRemainingMs: number,
  departureStation: number,
  unloadSpeedUpgradeCount: number,
  destinationMark: number = CART_MARK_X,
  returnStation: number = departureStation,
): number {
  const leg =
    tripPhaseFor({
      ...initialSnapshot(),
      haulRemainingMs,
      unloadSpeedUpgradeCount,
    })?.leg ?? "back";
  const unloadMs = unloadMsFor(unloadSpeedUpgradeCount);
  const halfTravel = HAUL_TRAVEL_MS / 2;
  const walkPxPerMs = HAULER_WALK_PX_PER_MS;
  const tripMs = HAUL_TRAVEL_MS + unloadMs;

  if (leg === "out") {
    return Math.max(
      destinationMark,
      Math.round(departureStation - (tripMs - haulRemainingMs) * walkPxPerMs),
    );
  }
  if (leg === "unload") {
    return destinationMark;
  }
  return Math.min(
    returnStation,
    Math.round(destinationMark + (halfTravel - haulRemainingMs) * walkPxPerMs),
  );
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
  atGrabStation: boolean = true,
): boolean {
  return (
    haulRemainingMs === 0 &&
    heapLoads >= 1 &&
    atGrabStation &&
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
  const spillExpiryByBodyId = new Map<number, number>();
  let carriedVariantIndexes: number[] = [];
  let haulerLeftPx = HAULER_MARK_X;
  let haulerSteppedToMs = 0;
  let heldBodyId: number | undefined;
  /** Walk target locked when the held Ore is chosen — pile settle must not
      retarget the Hauler mid-approach (idle↔walk thrash). */
  let heldWalkStationPx: number | null = null;
  let removedHeldBody = false;
  let haulDepartureStation: number | null = null;
  let haulReturnStation: number | null = null;
  let prevHaulRemainingMs = session.snapshot.haulRemainingMs;

  function trackHaulDeparture(nowMs: number): void {
    const remaining = session.snapshot.haulRemainingMs;
    if (prevHaulRemainingMs === 0 && remaining > 0) {
      haulDepartureStation = isTwoDwarf()
        ? haulerLeftPx
        : MINING_MARK_X;
      haulReturnStation = null;
    }
    if (prevHaulRemainingMs > 0 && remaining === 0) {
      if (isTwoDwarf()) {
        haulerLeftPx =
          haulReturnStation ?? haulDepartureStation ?? HAULER_MARK_X;
      }
      haulDepartureStation = null;
      haulReturnStation = null;
      haulerSteppedToMs = nowMs;
    }
    prevHaulRemainingMs = remaining;
  }

  function ensureHaulDepartureStation(): void {
    if (
      haulDepartureStation === null &&
      session.snapshot.haulRemainingMs > 0
    ) {
      haulDepartureStation = isTwoDwarf()
        ? haulerLeftPx
        : MINING_MARK_X;
    }
  }

  function minerLeftFor(_nowMs: number): number {
    const snap = session.snapshot;
    if (faceSlide < 1 || isTwoDwarf()) {
      return MINING_MARK_X;
    }
    if (snap.haulRemainingMs > 0) {
      ensureHaulDepartureStation();
      return tripLeftFor(
        snap.haulRemainingMs,
        MINING_MARK_X,
        snap.unloadSpeedUpgradeCount,
      );
    }
    return MINING_MARK_X;
  }

  function atGrabStation(): boolean {
    return (
      heldWalkStationPx !== null && haulerLeftPx === heldWalkStationPx
    );
  }

  function pileTargetCount(): number {
    const snap = session.snapshot;
    if (snap.crewSize !== 2) {
      return 0;
    }
    const liftedLoads = isPickupLifted(
      snap.haulRemainingMs,
      snap.heapLoads,
      snap.pickupProgressMs,
      snap.haulSpeedUpgradeCount,
      atGrabStation(),
    )
      ? Math.min(snap.heapLoads, grabSizeFor(snap.grabSizeUpgradeCount))
      : 0;
    return Math.min(
      Math.max(0, snap.heapLoads - liftedLoads),
      HEAP_RENDER_CEILING,
    );
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

  function haulerHandPoint(left: number): { x: number; y: number } {
    return {
      x: left + HAULER_HAND_DX + ORE_SIZE / 2,
      y: FLOOR_Y + HAULER_HAND_DY,
    };
  }

  function pickHeldBody(
    left: number,
    excluded: ReadonlySet<number>,
  ): number | null {
    return pickHeldBodies(left, excluded, 1)[0] ?? null;
  }

  function pickHeldBodies(
    left: number,
    excluded: ReadonlySet<number>,
    count: number,
  ): readonly number[] {
    const { x: handX, y: handY } = haulerHandPoint(left);
    return pile.bodies
      .filter((body) => !excluded.has(body.id))
      .sort((a, b) => {
        const aDist = (a.x - handX) ** 2 + (a.y - handY) ** 2;
        const bDist = (b.x - handX) ** 2 + (b.y - handY) ** 2;
        return aDist - bDist || a.id - b.id;
      })
      .slice(0, count)
      .map((body) => body.id);
  }

  function heldBodyStation(): number | null {
    if (heldBodyId === undefined) {
      return null;
    }
    const body = pile.bodies.find((b) => b.id === heldBodyId);
    if (!body) {
      return null;
    }
    return haulerStationFor(body.x);
  }

  /** Where the Hauler is headed between Trips: the Ore he Lifts next, or his
      stand by the Cart when the Heap has nothing for him. */
  function haulerWalkTarget(): number {
    return heldWalkStationPx ?? HAULER_MARK_X;
  }

  function clearHeldOre(): void {
    heldBodyId = undefined;
    heldWalkStationPx = null;
  }

  function assignHeldOre(bodyId: number | undefined): void {
    heldBodyId = bodyId;
    if (bodyId === undefined) {
      heldWalkStationPx = null;
      return;
    }
    heldWalkStationPx = heldBodyStation();
    removedHeldBody = false;
    // Seeded / restored mid-Lift: stand at the Ore rather than walking from the
    // Cart after the progress midpoint has already elapsed.
    const snap = session.snapshot;
    if (
      heldWalkStationPx !== null &&
      haulerLeftPx === HAULER_MARK_X &&
      snap.haulRemainingMs === 0 &&
      pickupProgressFraction(
        0,
        snap.pickupProgressMs,
        snap.haulSpeedUpgradeCount,
      ) > 0.5
    ) {
      haulerLeftPx = heldWalkStationPx;
    }
  }

  function takeCarriedFromPile(
    excluded: ReadonlySet<number>,
    count: number,
    liftedLoads: number,
    target: number,
  ): void {
    if (heldBodyId === undefined || removedHeldBody) {
      return;
    }
    if (!(count > target)) {
      if (carriedVariantIndexes.length === 0) {
        const variant = variantByBodyId.get(heldBodyId);
        if (variant !== undefined) {
          carriedVariantIndexes = [variant];
        }
      }
      return;
    }
    // Lift the Ore we walked to first; fill remaining Grab Size from nearest.
    const grabbed = new Set<number>();
    const bodyIds: number[] = [];
    if (pile.bodies.some((b) => b.id === heldBodyId && !excluded.has(b.id))) {
      bodyIds.push(heldBodyId);
      grabbed.add(heldBodyId);
    }
    if (bodyIds.length < liftedLoads) {
      bodyIds.push(
        ...pickHeldBodies(
          haulerLeftPx,
          new Set([...excluded, ...grabbed]),
          liftedLoads - bodyIds.length,
        ),
      );
    }
    for (const bodyId of bodyIds) {
      if (!pile.remove(bodyId)) {
        continue;
      }
      const variant = variantByBodyId.get(bodyId);
      if (variant !== undefined) {
        carriedVariantIndexes.push(variant);
        variantByBodyId.delete(bodyId);
      }
    }
    removedHeldBody = true;
  }

  function advanceHaulerLeft(nowMs: number): void {
    if (!isTwoDwarf()) {
      return;
    }
    if (session.snapshot.haulRemainingMs > 0) {
      haulerSteppedToMs = nowMs;
      return;
    }

    const dt = nowMs - haulerSteppedToMs;
    if (dt <= 0) {
      return;
    }

    const target = haulerWalkTarget();
    const maxMove = HAULER_WALK_PX_PER_MS * dt;
    const delta = target - haulerLeftPx;
    if (Math.abs(delta) <= maxMove) {
      haulerLeftPx = target;
    } else {
      haulerLeftPx += Math.sign(delta) * maxMove;
    }
    haulerSteppedToMs = nowMs;
  }

  function reconcilePile(nowMs: number): void {
    expireSpillBodies(nowMs);

    const snap = session.snapshot;
    const excluded = spillBodyIds();
    const inPickup = snap.haulRemainingMs === 0 && snap.heapLoads > 0;

    if (snap.heapLoads === 0 && snap.haulRemainingMs === 0) {
      // No snap home: advanceHaulerLeft walks him back at the one walk speed.
      clearHeldOre();
      removedHeldBody = false;
    }

    trackHaulDeparture(nowMs);
    ensureHaulDepartureStation();

    const haulLeg = tripPhaseFor(snap)?.leg ?? null;
    if (haulLeg === "back" && haulReturnStation === null) {
      assignHeldOre(pickHeldBody(HAULER_MARK_X, excluded) ?? undefined);
      haulReturnStation = heldWalkStationPx ?? HAULER_MARK_X;
    }

    if (inPickup) {
      const heldMissing =
        heldBodyId !== undefined &&
        !pile.bodies.some((b) => b.id === heldBodyId);
      const progressLifted = isPickupLifted(
        snap.haulRemainingMs,
        snap.heapLoads,
        snap.pickupProgressMs,
        snap.haulSpeedUpgradeCount,
        true,
      );
      // Acquire a target anytime we have none. Retarget only between Lifts —
      // during the Lift window the held body is removed and must not be
      // replaced by a neighbour (that caused idle↔walk thrash at the Ore).
      if (heldBodyId === undefined || (!progressLifted && heldMissing)) {
        assignHeldOre(pickHeldBody(haulerLeftPx, excluded) ?? undefined);
      }
    }

    advanceHaulerLeft(nowMs);

    const lifted = isPickupLifted(
      snap.haulRemainingMs,
      snap.heapLoads,
      snap.pickupProgressMs,
      snap.haulSpeedUpgradeCount,
      atGrabStation(),
    );

    const target = pileTargetCount();
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

    const grabSize = grabSizeFor(snap.grabSizeUpgradeCount);
    // Safety net: if the engine already departed mid-walk before the visual
    // Lift, still take the Ore so the out-leg is never empty-handed.
    const forceTripGrab =
      haulLeg === "out" &&
      carriedVariantIndexes.length === 0 &&
      heldBodyId !== undefined &&
      !removedHeldBody;
    const liftedLoads = lifted
      ? Math.min(snap.heapLoads, grabSize)
      : forceTripGrab
        ? Math.min(
            Math.max(1, snap.bagLoads),
            grabSize,
            pile.bodies.filter((b) => !excluded.has(b.id)).length || 1,
          )
        : 0;

    if ((lifted || forceTripGrab) && heldBodyId !== undefined) {
      const pileCount = pile.bodies.filter((b) => !excluded.has(b.id)).length;
      const pileTarget = lifted
        ? target
        : Math.max(0, pileCount - liftedLoads);
      takeCarriedFromPile(excluded, pileCount, liftedLoads, pileTarget);
    }

    // Deposit at the Cart stand during out (incl. early arrival), while still
    // facing west — avoids the east-facing hand jump that read as a shake.
    let atCartStand = false;
    if (haulLeg === "out" && haulDepartureStation !== null) {
      const outLeft = tripLeftFor(
        snap.haulRemainingMs,
        haulDepartureStation,
        snap.unloadSpeedUpgradeCount,
        HAULER_MARK_X,
        haulReturnStation ?? haulDepartureStation,
      );
      atCartStand = outLeft === HAULER_MARK_X;
    }
    const showCarried = lifted || (haulLeg === "out" && !atCartStand);
    if (!showCarried) {
      carriedVariantIndexes = [];
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

  function syncHaulerAnim(): void {
    if (!isTwoDwarf()) {
      return;
    }
    const snap = session.snapshot;
    if (snap.haulRemainingMs > 0) {
      const leg = tripPhaseFor(snap)!.leg;
      if (leg === "unload") {
        hauler.setHauling(null, simNowMs);
        return;
      }
      ensureHaulDepartureStation();
      const dest =
        leg === "out"
          ? HAULER_MARK_X
          : (haulReturnStation ?? haulDepartureStation ?? haulerLeftPx);
      const left =
        haulDepartureStation !== null
          ? tripLeftFor(
              snap.haulRemainingMs,
              haulDepartureStation,
              snap.unloadSpeedUpgradeCount,
              HAULER_MARK_X,
              haulReturnStation ?? haulDepartureStation,
            )
          : haulerLeftPx;
      // Arrived early for this leg — idle rather than walk-in-place stutter.
      // Keep west-facing on out arrival so carried Ore does not jump east.
      if (left === dest) {
        if (leg === "out") {
          hauler.setHauling("out", simNowMs);
          return;
        }
        hauler.setHauling(null, simNowMs);
        return;
      }
      hauler.setHauling(leg, simNowMs);
      return;
    }
    const target = haulerWalkTarget();
    if (haulerLeftPx !== target) {
      hauler.setHauling(haulerLeftPx < target ? "out" : "back", simNowMs);
      return;
    }
    hauler.setHauling(null, simNowMs);
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
    const remaining =
      snap.haulRemainingMs > 0
        ? Math.min(
            haulRoundTripMsFor(snap.unloadSpeedUpgradeCount),
            snap.haulRemainingMs + Math.max(0, simNowMs - nowMs),
          )
        : 0;
    const tripPhase = tripPhaseFor({ ...snap, haulRemainingMs: remaining });
    const phase: HaulerPhase = tripPhase?.leg ?? "pickup";
    const travelling = remaining > 0;
    const swingFrac = swingFractionAt(nowMs, travelling);

    let animation = hauler.animation;
    let facing = hauler.facing;
    if (phase === "pickup" && !travelling) {
      const target = haulerWalkTarget();
      if (haulerLeftPx !== target) {
        animation = "walk";
        facing = haulerLeftPx < target ? "east" : "west";
      } else {
        animation = "idle";
        facing = "east";
      }
    }

    let left = haulerLeftPx;
    if (travelling) {
      ensureHaulDepartureStation();
      if (haulDepartureStation !== null) {
        left = tripLeftFor(
          remaining,
          haulDepartureStation,
          snap.unloadSpeedUpgradeCount,
          HAULER_MARK_X,
          haulReturnStation ?? haulDepartureStation,
        );
      }
      // Mirror syncHaulerAnim: early arrival on out/back is idle, not walk.
      // Out/unload idle faces the Cart (west) until after deposit.
      if (phase === "out" && left === HAULER_MARK_X) {
        animation = "idle";
        facing = "west";
      } else if (phase === "unload") {
        animation = "idle";
        facing = "west";
      } else if (
        phase === "back" &&
        left === (haulReturnStation ?? haulDepartureStation)
      ) {
        animation = "idle";
        facing = "east";
      } else if (phase === "out") {
        animation = "walk";
        facing = "west";
      } else if (phase === "back") {
        animation = "walk";
        facing = "east";
      }
    }

    const frameIndex =
      animation === "idle" && (phase === "out" || phase === "unload")
        ? 0
        : frameIndexFor(hauler, nowMs, swingFrac);

    return {
      animation,
      facing,
      frameIndex,
      left,
      phase,
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
      ...(carriedVariantIndexes.length > 0
        ? { carriedVariantIndexes: [...carriedVariantIndexes] }
        : {}),
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
      trackHaulDeparture(simNowMs);
    },
  };
}

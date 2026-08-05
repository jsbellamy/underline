import {
  createDwarfAnimController,
  type DwarfAnimController,
  type DwarfAnimId,
  type DwarfFacing,
  type HaulAnimPhase,
} from "../core/dwarf-anim-state";
import {
  digRateFor,
  grabSizeFor,
  HAUL_TRAVEL_MS,
  pickupMsPerLoad,
  type MiningSnapshot,
} from "../core/mining-engine";
import { tripPhaseFor } from "../core/trip-phase";
import {
  FLOOR_Y,
  HAULER_HAND_DX,
  HAULER_HAND_DY,
  HAULER_MARK_X,
  HAULER_WALK_PX_PER_MS,
  haulerStationFor,
  ORE_SIZE,
} from "./pane-layout";
import { tripLeftFor } from "./trip-position";

export type HaulerPhase = "pickup" | "unload" | HaulAnimPhase;

export interface HeapBody {
  readonly id: number;
  readonly x: number;
  readonly y: number;
}

export interface LiftResult {
  /** Body ids taken this step, in Lift order; empty when nothing was lifted. */
  readonly liftedIds: readonly number[];
  /** True while carried Ore belongs in his hands. */
  readonly carrying: boolean;
}

export interface HaulerStance {
  /** Sprite left in Pane px. */
  readonly left: number;
  readonly animation: DwarfAnimId;
  readonly facing: DwarfFacing;
  readonly phase: HaulerPhase;
}

export interface HaulerChoreography {
  /** Latch Trip stations, step the walk, sync anim, and run the Lift. */
  advanceTo(
    snapshot: MiningSnapshot,
    nowMs: number,
    bodies: readonly HeapBody[],
  ): LiftResult;
  /** Stance at a presentation time at or after the last `advanceTo`. */
  stanceAt(snapshot: MiningSnapshot, nowMs: number): HaulerStance;
}

/** Presenter-only seam until frame index moves into stance. */
export interface HaulerChoreographyPresenterSeam {
  frameIndexAt(nowMs: number, swingFraction: number): number;
  setDigRate(digRate: number): void;
  willEnterBackLeg(snapshot: MiningSnapshot): boolean;
  liftedLoadCountForPile(snapshot: MiningSnapshot): number;
}

export function pickupProgressFraction(
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
  atGrabStation: boolean,
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

export function createHaulerChoreography(options: {
  digRate: number;
}): HaulerChoreography & HaulerChoreographyPresenterSeam {
  const hauler: DwarfAnimController = createDwarfAnimController({
    digRate: options.digRate,
  });
  let leftPx = HAULER_MARK_X;
  let steppedToMs = 0;
  let walkTarget: number | null = null;
  let haulDepartureStation: number | null = null;
  let haulReturnStation: number | null = null;
  let prevHaulRemainingMs = 0;
  let heldBodyId: number | undefined;
  /** Walk target locked when the held Ore is chosen — pile settle must not
      retarget the Hauler mid-approach (idle↔walk thrash). */
  let heldWalkStationPx: number | null = null;
  let removedHeldBody = false;

  function walkTargetPx(): number {
    return walkTarget ?? HAULER_MARK_X;
  }

  function haulerHandPoint(left: number): { x: number; y: number } {
    return {
      x: left + HAULER_HAND_DX + ORE_SIZE / 2,
      y: FLOOR_Y + HAULER_HAND_DY,
    };
  }

  function pickHeldBodies(
    left: number,
    bodies: readonly HeapBody[],
    excluded: ReadonlySet<number>,
    count: number,
  ): readonly number[] {
    const { x: handX, y: handY } = haulerHandPoint(left);
    return bodies
      .filter((body) => !excluded.has(body.id))
      .sort((a, b) => {
        const aDist = (a.x - handX) ** 2 + (a.y - handY) ** 2;
        const bDist = (b.x - handX) ** 2 + (b.y - handY) ** 2;
        return aDist - bDist || a.id - b.id;
      })
      .slice(0, count)
      .map((body) => body.id);
  }

  function pickHeldBody(
    left: number,
    bodies: readonly HeapBody[],
    excluded: ReadonlySet<number>,
  ): number | null {
    return pickHeldBodies(left, bodies, excluded, 1)[0] ?? null;
  }

  function heldBodyStation(bodies: readonly HeapBody[]): number | null {
    if (heldBodyId === undefined) {
      return null;
    }
    const body = bodies.find((b) => b.id === heldBodyId);
    if (!body) {
      return null;
    }
    return haulerStationFor(body.x);
  }

  function atGrabStation(): boolean {
    return (
      heldWalkStationPx !== null && leftPx === heldWalkStationPx
    );
  }

  function clearHeldOre(): void {
    heldBodyId = undefined;
    heldWalkStationPx = null;
    walkTarget = null;
  }

  function assignHeldOre(
    bodyId: number | undefined,
    bodies: readonly HeapBody[],
    snapshot: MiningSnapshot,
  ): void {
    heldBodyId = bodyId;
    if (bodyId === undefined) {
      walkTarget = null;
      return;
    }
    heldWalkStationPx = heldBodyStation(bodies);
    walkTarget = heldWalkStationPx;
    removedHeldBody = false;
    // Seeded / restored mid-Lift: stand at the Ore rather than walking from the
    // Cart after the progress midpoint has already elapsed.
    if (
      heldWalkStationPx !== null &&
      leftPx === HAULER_MARK_X &&
      snapshot.haulRemainingMs === 0 &&
      pickupProgressFraction(
        0,
        snapshot.pickupProgressMs,
        snapshot.haulSpeedUpgradeCount,
      ) > 0.5
    ) {
      leftPx = heldWalkStationPx;
    }
  }

  function liftedBodyIds(
    bodies: readonly HeapBody[],
    excluded: ReadonlySet<number>,
    liftedLoads: number,
  ): readonly number[] {
    if (heldBodyId === undefined || removedHeldBody) {
      return [];
    }
    const grabbed = new Set<number>();
    const bodyIds: number[] = [];
    if (bodies.some((b) => b.id === heldBodyId && !excluded.has(b.id))) {
      bodyIds.push(heldBodyId);
      grabbed.add(heldBodyId);
    }
    if (bodyIds.length < liftedLoads) {
      bodyIds.push(
        ...pickHeldBodies(
          leftPx,
          bodies,
          new Set([...excluded, ...grabbed]),
          liftedLoads - bodyIds.length,
        ),
      );
    }
    return bodyIds;
  }

  function trackHaulDeparture(snapshot: MiningSnapshot, nowMs: number): void {
    const remaining = snapshot.haulRemainingMs;
    if (prevHaulRemainingMs === 0 && remaining > 0) {
      haulDepartureStation = leftPx;
      haulReturnStation = null;
    }
    if (prevHaulRemainingMs > 0 && remaining === 0) {
      leftPx = haulReturnStation ?? haulDepartureStation ?? HAULER_MARK_X;
      haulDepartureStation = null;
      haulReturnStation = null;
      steppedToMs = nowMs;
    }
    prevHaulRemainingMs = remaining;
  }

  function ensureHaulDepartureStation(snapshot: MiningSnapshot): void {
    if (
      haulDepartureStation === null &&
      snapshot.haulRemainingMs > 0
    ) {
      haulDepartureStation = leftPx;
    }
  }

  function leftBetweenTripsAt(nowMs: number): number {
    const target = walkTargetPx();
    const elapsed = nowMs - steppedToMs;
    if (elapsed < 0) {
      return (
        leftPx -
        Math.sign(target - leftPx) * HAULER_WALK_PX_PER_MS * (-elapsed)
      );
    }
    if (elapsed === 0) {
      return leftPx;
    }
    const maxMove = HAULER_WALK_PX_PER_MS * elapsed;
    const delta = target - leftPx;
    if (Math.abs(delta) <= maxMove) {
      return target;
    }
    return leftPx + Math.sign(delta) * maxMove;
  }

  function advanceLeft(snapshot: MiningSnapshot, nowMs: number): void {
    if (snapshot.haulRemainingMs > 0) {
      steppedToMs = nowMs;
      return;
    }

    const dt = nowMs - steppedToMs;
    if (dt <= 0) {
      return;
    }

    const target = walkTargetPx();
    const maxMove = HAULER_WALK_PX_PER_MS * dt;
    const delta = target - leftPx;
    if (Math.abs(delta) <= maxMove) {
      leftPx = target;
    } else {
      leftPx += Math.sign(delta) * maxMove;
    }
    steppedToMs = nowMs;
  }

  function syncAnim(snapshot: MiningSnapshot, nowMs: number): void {
    if (snapshot.haulRemainingMs > 0) {
      const leg = tripPhaseFor(snapshot)!.leg;
      if (leg === "unload") {
        hauler.setHauling(null, nowMs);
        return;
      }
      ensureHaulDepartureStation(snapshot);
      const dest =
        leg === "out"
          ? HAULER_MARK_X
          : (haulReturnStation ?? haulDepartureStation ?? leftPx);
      const left =
        haulDepartureStation !== null
          ? tripLeftFor(
              snapshot.haulRemainingMs,
              haulDepartureStation,
              snapshot.unloadSpeedUpgradeCount,
              HAULER_MARK_X,
              haulReturnStation ?? haulDepartureStation,
            )
          : leftPx;
      if (left === dest) {
        if (leg === "out") {
          hauler.setHauling("out", nowMs);
          return;
        }
        hauler.setHauling(null, nowMs);
        return;
      }
      hauler.setHauling(leg, nowMs);
      return;
    }
    const target = walkTargetPx();
    if (leftPx !== target) {
      hauler.setHauling(leftPx < target ? "out" : "back", nowMs);
      return;
    }
    hauler.setHauling(null, nowMs);
  }

  function stanceFacingForTravel(
    phase: HaulerPhase,
    left: number,
    returnStation: number | null,
    departureStation: number | null,
  ): { animation: DwarfAnimId; facing: DwarfFacing } {
    if (phase === "out" && left === HAULER_MARK_X) {
      return { animation: "idle", facing: "west" };
    }
    if (phase === "unload") {
      return { animation: "idle", facing: "west" };
    }
    if (
      phase === "back" &&
      left === (returnStation ?? departureStation)
    ) {
      return { animation: "idle", facing: "east" };
    }
    if (phase === "out") {
      return { animation: "walk", facing: "west" };
    }
    if (phase === "back") {
      return { animation: "walk", facing: "east" };
    }
    return { animation: hauler.animation, facing: hauler.facing };
  }

  function enteredBackLegFrame(snapshot: MiningSnapshot): boolean {
    return enteringBackLegFrame(snapshot);
  }

  function enteringBackLegFrame(snapshot: MiningSnapshot): boolean {
    const halfTravel = HAUL_TRAVEL_MS / 2;
    return (
      snapshot.haulRemainingMs > 0 &&
      prevHaulRemainingMs > halfTravel &&
      snapshot.haulRemainingMs <= halfTravel
    );
  }

  function reconcileTargeting(
    snapshot: MiningSnapshot,
    bodies: readonly HeapBody[],
    enteringBackLeg: boolean,
  ): void {
    const excluded = new Set<number>();
    const inPickup = snapshot.haulRemainingMs === 0 && snapshot.heapLoads > 0;

    if (snapshot.heapLoads === 0 && snapshot.haulRemainingMs === 0) {
      clearHeldOre();
      removedHeldBody = false;
    }

    if (enteringBackLeg) {
      assignHeldOre(
        pickHeldBody(HAULER_MARK_X, bodies, excluded) ?? undefined,
        bodies,
        snapshot,
      );
    }

    if (inPickup) {
      const heldMissing =
        heldBodyId !== undefined &&
        !bodies.some((b) => b.id === heldBodyId);
      const progressLifted = isPickupLifted(
        snapshot.haulRemainingMs,
        snapshot.heapLoads,
        snapshot.pickupProgressMs,
        snapshot.haulSpeedUpgradeCount,
        true,
      );
      // Acquire a target anytime we have none. Retarget only between Lifts —
      // during the Lift window the held body is removed and must not be
      // replaced by a neighbour (that caused idle↔walk thrash at the Ore).
      if (heldBodyId === undefined || (!progressLifted && heldMissing)) {
        assignHeldOre(
          pickHeldBody(leftPx, bodies, excluded) ?? undefined,
          bodies,
          snapshot,
        );
      }
    }
  }

  function computeLiftResult(
    snapshot: MiningSnapshot,
    bodies: readonly HeapBody[],
  ): LiftResult {
    const excluded = new Set<number>();
    const haulLeg = tripPhaseFor(snapshot)?.leg ?? null;

    const lifted = isPickupLifted(
      snapshot.haulRemainingMs,
      snapshot.heapLoads,
      snapshot.pickupProgressMs,
      snapshot.haulSpeedUpgradeCount,
      atGrabStation(),
    );

    const grabSize = grabSizeFor(snapshot.grabSizeUpgradeCount);
    const forceTripGrab =
      haulLeg === "out" &&
      heldBodyId !== undefined &&
      !removedHeldBody;
    const liftedLoads = lifted
      ? Math.min(snapshot.heapLoads, grabSize)
      : forceTripGrab
        ? Math.min(
            Math.max(1, snapshot.bagLoads),
            grabSize,
            bodies.length || 1,
          )
        : 0;

    let liftedIds: readonly number[] = [];
    if ((lifted || forceTripGrab) && heldBodyId !== undefined) {
      liftedIds = liftedBodyIds(bodies, excluded, liftedLoads);
      if (liftedIds.length > 0) {
        removedHeldBody = true;
      }
    }

    let atCartStand = false;
    if (haulLeg === "out") {
      const outLeft =
        haulDepartureStation !== null
          ? tripLeftFor(
              snapshot.haulRemainingMs,
              haulDepartureStation,
              snapshot.unloadSpeedUpgradeCount,
              HAULER_MARK_X,
              haulReturnStation ?? haulDepartureStation,
            )
          : leftPx;
      atCartStand = outLeft === HAULER_MARK_X;
    }
    const carrying =
      lifted ||
      (forceTripGrab && liftedIds.length > 0) ||
      (haulLeg === "out" && !atCartStand);

    return { liftedIds, carrying };
  }

  const api: HaulerChoreography & HaulerChoreographyPresenterSeam = {
    setDigRate(digRate: number): void {
      hauler.setDigRate(digRate);
    },
    willEnterBackLeg(snapshot: MiningSnapshot): boolean {
      return enteredBackLegFrame(snapshot);
    },
    liftedLoadCountForPile(snapshot: MiningSnapshot): number {
      if (
        !isPickupLifted(
          snapshot.haulRemainingMs,
          snapshot.heapLoads,
          snapshot.pickupProgressMs,
          snapshot.haulSpeedUpgradeCount,
          atGrabStation(),
        )
      ) {
        return 0;
      }
      return Math.min(
        snapshot.heapLoads,
        grabSizeFor(snapshot.grabSizeUpgradeCount),
      );
    },
    frameIndexAt(nowMs: number, swingFraction: number): number {
      if (hauler.animation === "swing") {
        return hauler.frameIndexForSwingFraction(swingFraction);
      }
      return hauler.frameIndexAt(nowMs);
    },
    advanceTo(
      snapshot: MiningSnapshot,
      nowMs: number,
      bodies: readonly HeapBody[],
    ): LiftResult {
      hauler.setDigRate(digRateFor(snapshot.digRateUpgradeCount));
      const enteringBackLeg = enteringBackLegFrame(snapshot);
      trackHaulDeparture(snapshot, nowMs);
      reconcileTargeting(snapshot, bodies, enteringBackLeg);
      ensureHaulDepartureStation(snapshot);
      const haulLeg = tripPhaseFor(snapshot)?.leg ?? null;
      if (haulLeg === "back" && haulReturnStation === null) {
        haulReturnStation = walkTarget ?? HAULER_MARK_X;
      }
      advanceLeft(snapshot, nowMs);
      syncAnim(snapshot, nowMs);
      return computeLiftResult(snapshot, bodies);
    },
    stanceAt(snapshot: MiningSnapshot, nowMs: number): HaulerStance {
      const tripPhase = tripPhaseFor(snapshot);
      const phase: HaulerPhase = tripPhase?.leg ?? "pickup";
      const travelling = snapshot.haulRemainingMs > 0;

      let animation = hauler.animation;
      let facing = hauler.facing;

      let left = travelling ? leftPx : leftBetweenTripsAt(nowMs);
      if (travelling) {
        if (haulDepartureStation !== null) {
          left = tripLeftFor(
            snapshot.haulRemainingMs,
            haulDepartureStation,
            snapshot.unloadSpeedUpgradeCount,
            HAULER_MARK_X,
            haulReturnStation ?? haulDepartureStation,
          );
        }
        const travel = stanceFacingForTravel(
          phase,
          left,
          haulReturnStation,
          haulDepartureStation,
        );
        animation = travel.animation;
        facing = travel.facing;
      } else if (phase === "pickup") {
        const target = walkTargetPx();
        if (left !== target) {
          animation = "walk";
          facing = left < target ? "east" : "west";
        } else {
          animation = "idle";
          facing = "east";
        }
      }

      return { left, animation, facing, phase };
    },
  };

  return api;
}

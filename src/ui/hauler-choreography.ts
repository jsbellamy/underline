import {
  createDwarfAnimController,
  type DwarfAnimController,
  type DwarfAnimId,
  type DwarfFacing,
  type HaulAnimPhase,
} from "../core/dwarf-anim-state";
import {
  digRateFor,
  HAUL_TRAVEL_MS,
  type MiningSnapshot,
} from "../core/mining-engine";
import { tripPhaseFor } from "../core/trip-phase";
import {
  HAULER_MARK_X,
  HAULER_WALK_PX_PER_MS,
} from "./pane-layout";
import { tripLeftFor } from "./trip-position";

export type HaulerPhase = "pickup" | "unload" | HaulAnimPhase;

export interface HaulerStance {
  /** Sprite left in Pane px. */
  readonly left: number;
  readonly animation: DwarfAnimId;
  readonly facing: DwarfFacing;
  readonly phase: HaulerPhase;
}

export interface HaulerChoreography {
  /** Latch Trip stations, step the walk, and sync the anim clip to `nowMs`. */
  advanceTo(snapshot: MiningSnapshot, nowMs: number): void;
  /** Stance at a presentation time at or after the last `advanceTo`. */
  stanceAt(snapshot: MiningSnapshot, nowMs: number): HaulerStance;
  /** Walk destination between Trips; `null` parks him at `HAULER_MARK_X`. */
  setWalkTarget(px: number | null): void;
  /** Current sprite left — the presenter's Ore-picking origin until the
      follow-up slice. */
  readonly leftPx: number;
}

/** Presenter-only seam until frame index and mid-Lift snap move into stance. */
export interface HaulerChoreographyPresenterSeam {
  frameIndexAt(nowMs: number, swingFraction: number): number;
  setDigRate(digRate: number): void;
  snapToWalkTarget(): void;
  willEnterBackLeg(snapshot: MiningSnapshot): boolean;
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

  function walkTargetPx(): number {
    return walkTarget ?? HAULER_MARK_X;
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
    const halfTravel = HAUL_TRAVEL_MS / 2;
    return (
      snapshot.haulRemainingMs > 0 &&
      prevHaulRemainingMs > halfTravel &&
      snapshot.haulRemainingMs <= halfTravel
    );
  }

  const api: HaulerChoreography & HaulerChoreographyPresenterSeam = {
    get leftPx() {
      return leftPx;
    },
    setWalkTarget(px: number | null): void {
      walkTarget = px;
    },
    snapToWalkTarget(): void {
      leftPx = walkTargetPx();
    },
    setDigRate(digRate: number): void {
      hauler.setDigRate(digRate);
    },
    willEnterBackLeg(snapshot: MiningSnapshot): boolean {
      return enteredBackLegFrame(snapshot);
    },
    frameIndexAt(nowMs: number, swingFraction: number): number {
      if (hauler.animation === "swing") {
        return hauler.frameIndexForSwingFraction(swingFraction);
      }
      return hauler.frameIndexAt(nowMs);
    },
    advanceTo(snapshot: MiningSnapshot, nowMs: number): void {
      hauler.setDigRate(digRateFor(snapshot.digRateUpgradeCount));
      trackHaulDeparture(snapshot, nowMs);
      ensureHaulDepartureStation(snapshot);
      const haulLeg = tripPhaseFor(snapshot)?.leg ?? null;
      if (haulLeg === "back" && haulReturnStation === null) {
        haulReturnStation = walkTarget ?? HAULER_MARK_X;
      }
      advanceLeft(snapshot, nowMs);
      syncAnim(snapshot, nowMs);
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

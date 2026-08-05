import { describe, expect, it } from "vitest";
import {
  haulRoundTripMsFor,
  initialSnapshot,
} from "../core/mining-engine";
import {
  HAULER_MARK_X,
  HAULER_WALK_PX_PER_MS,
} from "./pane-layout";
import { tripLeftFor } from "./trip-position";
import {
  createHaulerChoreography,
  type HaulerChoreography,
} from "./hauler-choreography";

const twoDwarfSnap = () => ({ ...initialSnapshot(), crewSize: 2 });

function advanceChoreography(
  choreography: HaulerChoreography,
  snapshotOverrides: Record<string, unknown> = {},
  nowMs: number,
): void {
  choreography.advanceTo({ ...twoDwarfSnap(), ...snapshotOverrides }, nowMs);
}

describe("hauler choreography", () => {
  it("walks toward setWalkTarget at HAULER_WALK_PX_PER_MS between Trips", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const walkTarget = HAULER_MARK_X + 80;
    choreography.setWalkTarget(walkTarget);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      500,
    );
    const stance = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 1 },
      500,
    );
    const moved = stance.left - HAULER_MARK_X;
    expect(moved).toBe(Math.round(500 * HAULER_WALK_PX_PER_MS));
    expect(stance.animation).toBe("walk");
    expect(stance.facing).toBe("east");
    expect(stance.phase).toBe("pickup");
  });

  it("faces west on the out leg and east on the back leg while travelling", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const departure = HAULER_MARK_X + 60;
    choreography.setWalkTarget(departure);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    );
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
    );
    const outRemaining = tripMs - 100;
    const outStance = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: outRemaining, heapLoads: 0 },
      2_000 + tripMs - outRemaining,
    );
    expect(outStance.phase).toBe("out");
    expect(outStance.animation).toBe("walk");
    expect(outStance.facing).toBe("west");

    choreography.setWalkTarget(HAULER_MARK_X + 40);
    const backRemaining = 1_900;
    advanceChoreography(
      choreography,
      { haulRemainingMs: backRemaining, heapLoads: 0 },
      2_000 + tripMs - backRemaining,
    );
    const backStance = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: backRemaining, heapLoads: 0 },
      2_000 + tripMs - backRemaining,
    );
    expect(backStance.phase).toBe("back");
    expect(backStance.animation).toBe("walk");
    expect(backStance.facing).toBe("east");
  });

  it("idles facing west at early out-leg arrival on the Hauler stand", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const departure = HAULER_MARK_X + 60;
    choreography.setWalkTarget(departure);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    );
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
    );
    const outRemaining =
      tripMs - Math.ceil(60 / HAULER_WALK_PX_PER_MS);
    const stance = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: outRemaining, heapLoads: 0 },
      2_000 + tripMs - outRemaining,
    );
    expect(stance.left).toBe(HAULER_MARK_X);
    expect(stance.animation).toBe("idle");
    expect(stance.facing).toBe("west");
    expect(stance.phase).toBe("out");
  });

  it("stanceAt is idempotent for equal nowMs and does not advance position", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    choreography.setWalkTarget(HAULER_MARK_X + 100);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      200,
    );
    const snap = { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 1 };
    const first = choreography.stanceAt(snap, 200);
    const second = choreography.stanceAt(snap, 200);
    expect(second).toEqual(first);
    advanceChoreography(choreography, snap, 400);
    expect(choreography.stanceAt(snap, 200).left).toBe(first.left);
  });

  it("resumes at the return station after a Trip ends", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const departure = HAULER_MARK_X + 60;
    const returnStation = HAULER_MARK_X + 40;
    choreography.setWalkTarget(departure);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    );
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
    );
    choreography.setWalkTarget(returnStation);
    const backRemaining = 1_000;
    const backStartMs = 2_000 + tripMs - backRemaining;
    advanceChoreography(
      choreography,
      { haulRemainingMs: backRemaining, heapLoads: 0 },
      backStartMs,
    );
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      backStartMs + backRemaining,
    );
    expect(choreography.leftPx).toBe(returnStation);
  });

  it("positions on a Trip from tripLeftFor with HAULER_MARK_X as destination", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const departure = HAULER_MARK_X + 72;
    choreography.setWalkTarget(departure);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    );
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
    );
    const remaining = tripMs - 800;
    const expectedLeft = tripLeftFor(
      remaining,
      departure,
      0,
      HAULER_MARK_X,
      departure,
    );
    const stance = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: remaining, heapLoads: 0 },
      2_000 + 800,
    );
    expect(stance.left).toBe(expectedLeft);
  });
});

import { describe, expect, it } from "vitest";
import { createHeapPileSim } from "../core/heap-pile-sim";
import {
  haulRoundTripMsFor,
  initialSnapshot,
  pickupMsPerLoad,
} from "../core/mining-engine";
import { heapOreRadius } from "./heap-ore-variants";
import {
  FLOOR_Y,
  HAULER_HAND_DX,
  HAULER_HAND_DY,
  HAULER_MARK_X,
  HAULER_WALK_PX_PER_MS,
  HEAP_BIN_CEILING_Y,
  HEAP_BIN_EAST_X,
  HEAP_BIN_FLOOR_Y,
  HEAP_BIN_WEST_X,
  HEAP_PILE_SEED,
  HEAP_SPAWN_X,
  haulerStationFor,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";
import { tripLeftFor } from "./trip-position";
import {
  createHaulerChoreography,
  pickupProgressFraction,
  type HeapBody,
  type HaulerChoreography,
} from "./hauler-choreography";

const twoDwarfSnap = () => ({ ...initialSnapshot(), crewSize: 2 });
const OPENING_PICKUP_MS = pickupMsPerLoad(0);
const PICKUP_QUARTER_MS = OPENING_PICKUP_MS * 0.25;
const PICKUP_THREE_QUARTER_MS = OPENING_PICKUP_MS * 0.75;

function advanceChoreography(
  choreography: HaulerChoreography,
  snapshotOverrides: Record<string, unknown> = {},
  nowMs: number,
  bodies: readonly HeapBody[] = [],
) {
  return choreography.advanceTo(
    { ...twoDwarfSnap(), ...snapshotOverrides },
    nowMs,
    bodies,
  );
}

function settledBodies(count: number): HeapBody[] {
  const pile = createHeapPileSim({
    bin: {
      floorY: HEAP_BIN_FLOOR_Y,
      westX: HEAP_BIN_WEST_X,
      eastX: HEAP_BIN_EAST_X,
      ceilingY: HEAP_BIN_CEILING_Y,
    },
    seed: HEAP_PILE_SEED,
  });
  for (let v = 0; v < count; v += 1) {
    pile.spawnJittered(heapOreRadius(v % 6), HEAP_SPAWN_X, ORE_SPAWN_BOTTOM);
  }
  pile.settle();
  return pile.bodies.map((b) => ({ id: b.id, x: b.x, y: b.y }));
}

function nearestBodyId(
  bodies: readonly HeapBody[],
  left: number,
): number {
  const handX = left + HAULER_HAND_DX + ORE_SIZE / 2;
  const handY = FLOOR_Y + HAULER_HAND_DY;
  let nearestId = bodies[0]!.id;
  let nearestDist = Infinity;
  for (const body of bodies) {
    const dist =
      (body.x - handX) * (body.x - handX) +
      (body.y - handY) * (body.y - handY);
    if (
      dist < nearestDist ||
      (dist === nearestDist && body.id < nearestId)
    ) {
      nearestDist = dist;
      nearestId = body.id;
    }
  }
  return nearestId;
}

describe("hauler choreography", () => {
  it("walks toward the nearest Heap body at HAULER_WALK_PX_PER_MS between Trips", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(1);
    const walkTarget = haulerStationFor(bodies[0]!.x);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0, bodies);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      500,
      bodies,
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
    expect(stance.left).toBeLessThan(walkTarget + 1);
  });

  it("faces west on the out leg and east on the back leg while travelling", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(1);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0, bodies);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
      bodies,
    );
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
      bodies,
    );
    const outRemaining = tripMs - 100;
    const outStance = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: outRemaining, heapLoads: 0 },
      2_000 + tripMs - outRemaining,
    );
    expect(outStance.phase).toBe("out");
    expect(outStance.animation).toBe("walk");
    expect(outStance.facing).toBe("west");

    const returnBodies = settledBodies(2);
    const backRemaining = 1_900;
    advanceChoreography(
      choreography,
      { haulRemainingMs: backRemaining, heapLoads: 0 },
      2_000 + tripMs - backRemaining,
      returnBodies,
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
    const bodies = settledBodies(1);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0, bodies);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
      bodies,
    );
    const departure = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    ).left;
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
      bodies,
    );
    const outRemaining =
      tripMs - Math.ceil((departure - HAULER_MARK_X) / HAULER_WALK_PX_PER_MS);
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
    const bodies = settledBodies(3);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 3 }, 0, bodies);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 3 },
      200,
      bodies,
    );
    const snap = { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 3 };
    const first = choreography.stanceAt(snap, 200);
    const second = choreography.stanceAt(snap, 200);
    expect(second).toEqual(first);
    advanceChoreography(choreography, snap, 400, bodies);
    expect(choreography.stanceAt(snap, 200).left).toBe(first.left);
  });

  it("resumes at the return station after a Trip ends", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(2);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0, bodies);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
      bodies,
    );
    const departure = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    ).left;
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
      bodies,
    );
    const backRemaining = 1_000;
    const backStartMs = 2_000 + tripMs - backRemaining;
    advanceChoreography(
      choreography,
      { haulRemainingMs: backRemaining, heapLoads: 0 },
      backStartMs,
      bodies,
    );
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      backStartMs + backRemaining,
      bodies,
    );
    const returned = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 1 },
      backStartMs + backRemaining,
    );
    expect(returned.left).toBe(departure);
  });

  it("positions on a Trip from tripLeftFor with HAULER_MARK_X as destination", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(1);
    advanceChoreography(choreography, { haulRemainingMs: 0, heapLoads: 1 }, 0, bodies);
    advanceChoreography(
      choreography,
      { haulRemainingMs: 0, heapLoads: 1 },
      2_000,
      bodies,
    );
    const departure = choreography.stanceAt(
      { ...twoDwarfSnap(), haulRemainingMs: 0, heapLoads: 1 },
      2_000,
    ).left;
    const tripMs = haulRoundTripMsFor(0);
    advanceChoreography(
      choreography,
      { haulRemainingMs: tripMs, heapLoads: 0 },
      2_000,
      bodies,
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

  it("targets the nearest Heap body to the hand point", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(5);
    const nearestId = nearestBodyId(bodies, HAULER_MARK_X);
    const nearest = bodies.find((b) => b.id === nearestId)!;
    const target = haulerStationFor(nearest.x);
    advanceChoreography(choreography, { heapLoads: 5 }, 0, bodies);
    advanceChoreography(choreography, { heapLoads: 5 }, 5_000, bodies);
    const stance = choreography.stanceAt(
      { ...twoDwarfSnap(), heapLoads: 5 },
      5_000,
    );
    expect(stance.left).toBe(target);
  });

  it("a Lift in progress does not retarget to a nearer Load", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(8);
    const snap = { ...twoDwarfSnap(), heapLoads: 8 };
    advanceChoreography(choreography, snap, 0, bodies);
    advanceChoreography(
      choreography,
      snap,
      2_000,
      bodies.filter((b) => b.id !== bodies[0]!.id),
    );
    const atOre = choreography.stanceAt(snap, 2_000);
    const lift = advanceChoreography(
      choreography,
      {
        ...snap,
        pickupProgressMs: PICKUP_THREE_QUARTER_MS,
      },
      2_000 + PICKUP_QUARTER_MS,
      bodies.filter((b) => b.id !== bodies[0]!.id),
    );
    expect(lift.liftedIds).toHaveLength(1);
    expect(lift.liftedIds[0]).toBe(nearestBodyId(bodies, atOre.left));
    const afterLift = choreography.stanceAt(
      {
        ...snap,
        pickupProgressMs: PICKUP_THREE_QUARTER_MS,
      },
      2_000 + PICKUP_QUARTER_MS,
    );
    expect(afterLift.left).toBe(atOre.left);
    expect(afterLift.animation).toBe("idle");
  });

  it("Lifts the walked-to Load first then fills Grab Size from nearest bodies", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(5);
    const snap = {
      ...twoDwarfSnap(),
      heapLoads: 5,
      grabSizeUpgradeCount: 1,
    };
    advanceChoreography(choreography, snap, 0, bodies);
    advanceChoreography(choreography, snap, 5_000, bodies);
    const atStation = choreography.stanceAt(snap, 5_000);
    const lift = advanceChoreography(
      choreography,
      { ...snap, pickupProgressMs: PICKUP_THREE_QUARTER_MS },
      5_000 + PICKUP_QUARTER_MS,
      bodies,
    );
    expect(lift.liftedIds[0]).toBe(nearestBodyId(bodies, atStation.left));
    expect(lift.liftedIds).toHaveLength(2);
  });

  it("still takes Ore on the out leg if the engine departed before the visual Lift", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(1);
    const snap = {
      ...twoDwarfSnap(),
      heapLoads: 1,
      haulSpeedUpgradeCount: 3,
    };
    advanceChoreography(choreography, snap, 0, bodies);
    advanceChoreography(choreography, snap, 2_000, bodies);
    const tripMs = haulRoundTripMsFor(0);
    const outLift = advanceChoreography(
      choreography,
      { ...snap, haulRemainingMs: tripMs, heapLoads: 0, bagLoads: 1 },
      2_000,
      bodies,
    );
    expect(outLift.liftedIds).toHaveLength(1);
    expect(outLift.carrying).toBe(true);
  });

  it("stands at the target when restored past the pickup midpoint", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(3);
    const snap = {
      ...twoDwarfSnap(),
      heapLoads: 3,
      pickupProgressMs: PICKUP_THREE_QUARTER_MS,
    };
    advanceChoreography(choreography, snap, 0, bodies);
    const stance = choreography.stanceAt(snap, 0);
    const nearest = bodies.find(
      (b) => b.id === nearestBodyId(bodies, HAULER_MARK_X),
    )!;
    expect(stance.left).toBe(haulerStationFor(nearest.x));
    expect(stance.animation).toBe("idle");
  });

  it("releases carried Ore when the Hauler reaches the Cart stand during out", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(1);
    advanceChoreography(choreography, { heapLoads: 1 }, 0, bodies);
    advanceChoreography(choreography, { heapLoads: 1 }, 2_000, bodies);
    const departure = choreography.stanceAt(
      { ...twoDwarfSnap(), heapLoads: 1 },
      2_000,
    ).left;
    const lifted = advanceChoreography(
      choreography,
      { heapLoads: 1, pickupProgressMs: PICKUP_THREE_QUARTER_MS },
      2_000 + PICKUP_QUARTER_MS,
      bodies.slice(1),
    );
    expect(lifted.carrying).toBe(true);
    const tripMs = haulRoundTripMsFor(0);
    const outRemaining =
      tripMs - Math.ceil((departure - HAULER_MARK_X) / HAULER_WALK_PX_PER_MS);
    const outAtStand = advanceChoreography(
      choreography,
      { haulRemainingMs: outRemaining, heapLoads: 0 },
      2_000 + OPENING_PICKUP_MS + (tripMs - outRemaining),
      bodies.slice(1),
    );
    expect(outAtStand.carrying).toBe(false);
  });

  it("does not thrash idle/walk chasing a settling Ore station", () => {
    const choreography = createHaulerChoreography({ digRate: 1 });
    const bodies = settledBodies(8);
    const snap = { ...twoDwarfSnap(), heapLoads: 8 };
    const stepMs = 16;
    const rows: Array<{ animation: string; phase: string }> = [];
    let nowMs = 0;
    for (let i = 0; i < 500; i += 1) {
      advanceChoreography(choreography, snap, nowMs, bodies);
      const stance = choreography.stanceAt(snap, nowMs);
      rows.push({ animation: stance.animation, phase: stance.phase });
      nowMs += stepMs;
    }
    const pickup = rows.filter((r) => r.phase === "pickup");
    let arrived = false;
    let idleToWalkAfterArrival = 0;
    for (let i = 1; i < pickup.length; i += 1) {
      const prev = pickup[i - 1]!;
      const cur = pickup[i]!;
      if (prev.animation === "walk" && cur.animation === "idle") {
        arrived = true;
      }
      if (
        arrived &&
        prev.animation === "idle" &&
        cur.animation === "walk"
      ) {
        idleToWalkAfterArrival += 1;
      }
    }
    expect(idleToWalkAfterArrival).toBe(0);
  });

  it("exports pickupProgressFraction for the presenter snapshot", () => {
    expect(
      pickupProgressFraction(0, PICKUP_QUARTER_MS, 0),
    ).toBeCloseTo(0.25, 5);
    expect(pickupProgressFraction(1_000, PICKUP_QUARTER_MS, 0)).toBe(0);
  });
});

import { describe, expect, it } from "vitest";
import {
  createHeapPileSim,
  HEAP_GRAVITY,
  HEAP_LINEAR_DAMPING,
  HEAP_REST_SPEED,
  HEAP_RESTITUTION,
  HEAP_FRICTION,
  HEAP_CONTACT_ITERATIONS,
  HEAP_SETTLE_MAX_STEPS,
  HEAP_SIM_DT_MS,
  HEAP_SPAWN_JITTER_PX,
  HEAP_SPAWN_VX_MAX,
  HEAP_SPAWN_VX_MIN,
  mulberry32,
  type HeapBin,
} from "./heap-pile-sim";
import {
  HAULER_MARK_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  PANE_HEIGHT,
} from "../ui/pane-layout";

function paneBin(): HeapBin {
  return {
    floorY: HEAP_BOTTOM,
    westX: HAULER_MARK_X,
    eastX: HEAP_EAST_X,
    ceilingY: PANE_HEIGHT,
  };
}

function wideBin(): HeapBin {
  return {
    floorY: 8,
    westX: 0,
    eastX: 240,
    ceilingY: 112,
  };
}

describe("heap pile sim constants", () => {
  it("exports tuning constants from the contract table", () => {
    expect(HEAP_SIM_DT_MS).toBe(8);
    expect(HEAP_GRAVITY).toBe(0.0012);
    expect(HEAP_RESTITUTION).toBe(0.2);
    expect(HEAP_FRICTION).toBe(0.4);
    expect(HEAP_LINEAR_DAMPING).toBe(0.999);
    expect(HEAP_REST_SPEED).toBe(0.002);
    expect(HEAP_CONTACT_ITERATIONS).toBe(4);
    expect(HEAP_SETTLE_MAX_STEPS).toBe(2000);
    expect(HEAP_SPAWN_JITTER_PX).toBe(10);
    expect(HEAP_SPAWN_VX_MIN).toBe(-0.06);
    expect(HEAP_SPAWN_VX_MAX).toBe(-0.02);
  });
});

describe("heap pile sim coordinates", () => {
  it("falls with gravity toward decreasing y (y-up pane)", () => {
    const sim = createHeapPileSim({ bin: paneBin(), seed: 1, startMs: 0 });
    sim.spawn(6, 300, 80, 0, 0);
    const yBefore = sim.bodies[0]!.y;
    sim.stepTo(HEAP_SIM_DT_MS);
    expect(sim.bodies[0]!.y).toBeLessThan(yBefore);
  });
});

describe("heap pile sim integration", () => {
  it("integrates one body under gravity with no contacts", () => {
    const bin: HeapBin = {
      floorY: -1000,
      westX: -1000,
      eastX: 1000,
      ceilingY: 1000,
    };
    const sim = createHeapPileSim({ bin, seed: 1, startMs: 0 });
    sim.spawn(1, 50, 100, 0, 0);

    const expectAt = (steps: number, y: number, vy: number) => {
      sim.stepTo(steps * HEAP_SIM_DT_MS);
      const body = sim.bodies[0]!;
      expect(body.y).toBe(y);
      expect(body.vy).toBe(vy);
      expect(body.x).toBe(50);
      expect(body.vx).toBe(0);
    };

    sim.stepTo(0);
    expectAt(1, 99.9232768, -0.009590399999999999);
    expectAt(10, 95.7928580447547, -0.09547358083643075);
    expectAt(31, 62.32309628667064, -0.29288567270854227);
  });
});

describe("heap pile sim contacts", () => {
  it("resolves two overlapping bodies with hand-computed centres and velocities", () => {
    const bin: HeapBin = {
      floorY: -1000,
      westX: -1000,
      eastX: 1000,
      ceilingY: 1000,
    };
    const sim = createHeapPileSim({ bin, seed: 1, startMs: 0 });
    sim.spawn(10, 0, 0, 1, 0);
    sim.spawn(10, 15, 0, -1, 0);
    sim.stepTo(0);

    const sorted = [...sim.bodies].sort((a, b) => a.id - b.id);
    expect(sorted[0]!.x).toBe(-2.5);
    expect(sorted[0]!.y).toBe(0);
    expect(sorted[0]!.vx).toBe(-0.19999999999999996);
    expect(sorted[0]!.vy).toBe(0);
    expect(sorted[1]!.x).toBe(17.5);
    expect(sorted[1]!.y).toBe(0);
    expect(sorted[1]!.vx).toBe(0.19999999999999996);
    expect(sorted[1]!.vy).toBe(0);
  });

  it("resolves each wall with restitution and friction", () => {
    const bin = wideBin();

    const west = createHeapPileSim({ bin, seed: 1, startMs: 0 });
    west.spawn(10, 5, 50, -0.5, 0.3);
    west.stepTo(HEAP_SIM_DT_MS);
    let body = west.bodies[0]!;
    expect(body.x).toBe(10.7992);
    expect(body.y).toBe(50.8823168);
    expect(body.vx).toBe(0.0999);
    expect(body.vy).toBe(0.1102896);

    const east = createHeapPileSim({ bin, seed: 1, startMs: 0 });
    east.spawn(10, 235, 50, 0.5, 0.3);
    east.stepTo(HEAP_SIM_DT_MS);
    body = east.bodies[0]!;
    expect(body.x).toBe(229.2008);
    expect(body.vx).toBe(-0.0999);
    expect(body.vy).toBe(0.1102896);

    const floor = createHeapPileSim({ bin, seed: 1, startMs: 0 });
    floor.spawn(10, 50, 15, 0.3, -0.5);
    floor.stepTo(HEAP_SIM_DT_MS);
    body = floor.bodies[0]!;
    expect(body.y).toBe(18.7224768);
    expect(body.x).toBe(50.95904);
    expect(body.vx).toBe(0.11988);
    expect(body.vy).toBe(0.0903096);

    const ceiling = createHeapPileSim({ bin, seed: 1, startMs: 0 });
    ceiling.spawn(10, 50, 105, 0.3, 0.5);
    ceiling.stepTo(HEAP_SIM_DT_MS);
    body = ceiling.bodies[0]!;
    expect(body.y).toBe(101.1240768);
    expect(body.x).toBe(50.95904);
    expect(body.vx).toBe(0.11988);
    expect(body.vy).toBe(-0.1094904);
  });
});

describe("heap pile sim containment", () => {
  it("keeps every body inside the bin across 500 violent steps", () => {
    const bin = wideBin();
    const sim = createHeapPileSim({ bin, seed: 42, startMs: 0 });
    sim.spawn(8, 120, 60, 0.8, -0.9);
    sim.spawn(12, 80, 90, -1.2, 0.7);
    sim.spawn(6, 200, 40, 0.5, 1.1);

    for (let t = HEAP_SIM_DT_MS; t <= 500 * HEAP_SIM_DT_MS; t += HEAP_SIM_DT_MS) {
      sim.stepTo(t);
      for (const body of sim.bodies) {
        expect(body.x).toBeGreaterThanOrEqual(bin.westX + body.radius);
        expect(body.x).toBeLessThanOrEqual(bin.eastX - body.radius);
        expect(body.y).toBeGreaterThanOrEqual(bin.floorY + body.radius);
        expect(body.y).toBeLessThanOrEqual(bin.ceilingY - body.radius);
      }
    }
  });
});

describe("heap pile sim chunk neutrality", () => {
  it("matches one large stepTo to many small stepTo calls at the same end time", () => {
    const bin = wideBin();
    const build = () => {
      const sim = createHeapPileSim({ bin, seed: 7, startMs: 0 });
      sim.spawnJittered(8, 120, 80);
      sim.spawnJittered(10, 100, 85);
      sim.spawnJittered(6, 140, 75);
      return sim;
    };

    const single = build();
    single.stepTo(4000);

    const chunked = build();
    chunked.stepTo(500);
    chunked.stepTo(1200);
    chunked.stepTo(1800);
    chunked.stepTo(2500);
    chunked.stepTo(4000);

    expect(chunked.bodies).toEqual(single.bodies);
    expect(chunked.nowMs).toBe(4000);
    expect(single.nowMs).toBe(4000);
  });
});

describe("heap pile sim monotonic time", () => {
  it("throws on decreasing nowMs and performs no steps when equal", () => {
    const sim = createHeapPileSim({ bin: paneBin(), seed: 1, startMs: 100 });
    sim.spawn(6, 300, 80, 0, 0);
    sim.stepTo(200);
    const bodiesAfterFirst = sim.bodies;

    sim.stepTo(200);
    expect(sim.bodies).toEqual(bodiesAfterFirst);
    expect(sim.nowMs).toBe(200);

    expect(() => sim.stepTo(150)).toThrow(/cannot decrease/i);
    expect(sim.nowMs).toBe(200);
    expect(sim.bodies).toEqual(bodiesAfterFirst);
  });
});

describe("heap pile sim seeded jitter", () => {
  it("draws the first four mulberry32(1) values in order", () => {
    const rng = mulberry32(1);
    expect(rng()).toBe(0.6270739405881613);
    expect(rng()).toBe(0.002735721180215478);
    expect(rng()).toBe(0.5274470399599522);
    expect(rng()).toBe(0.9810509674716741);
  });

  it("produces identical bodies for the same seed and call sequence", () => {
    const bin = paneBin();
    const build = () => {
      const sim = createHeapPileSim({ bin, seed: 1, startMs: 0 });
      sim.spawnJittered(8, 350, 56);
      sim.spawnJittered(8, 330, 56);
      sim.stepTo(250);
      return sim.bodies;
    };
    expect(build()).toEqual(build());
  });
});

describe("heap pile sim grab selection", () => {
  it("chooses the topmost body inside reach", () => {
    const sim = createHeapPileSim({ bin: wideBin(), seed: 1, startMs: 0 });
    sim.spawn(6, 100, 20, 0, 0);
    sim.spawn(6, 105, 40, 0, 0);
    sim.spawn(6, 200, 50, 0, 0);
    expect(sim.removeGrabbed(104, 8)).toBe(2);
  });

  it("falls back to the topmost overall when nothing is in reach", () => {
    const sim = createHeapPileSim({ bin: wideBin(), seed: 1, startMs: 0 });
    sim.spawn(6, 50, 20, 0, 0);
    sim.spawn(6, 180, 45, 0, 0);
    expect(sim.removeGrabbed(10, 5)).toBe(2);
  });

  it("breaks height ties to the smallest x then smallest id", () => {
    const sim = createHeapPileSim({ bin: wideBin(), seed: 1, startMs: 0 });
    sim.spawn(6, 120, 30, 0, 0);
    sim.spawn(6, 80, 30, 0, 0);
    sim.spawn(6, 80, 30, 0, 0);
    expect(sim.removeGrabbed(100, 50)).toBe(2);
  });

  it("returns null on an empty pile", () => {
    const sim = createHeapPileSim({ bin: wideBin(), seed: 1, startMs: 0 });
    expect(sim.removeGrabbed(100, 20)).toBeNull();
  });
});

describe("heap pile sim settling", () => {
  it("rests 24 bodies inside the settle cap without advancing nowMs", () => {
    const bin = wideBin();
    const sim = createHeapPileSim({ bin, seed: 99, startMs: 500 });
    const radii = [6, 7, 8, 9, 10, 11, 12, 13, 14, 6, 7, 8, 9, 10, 11, 12, 13, 14, 6, 7, 8, 9, 10, 11];
    for (let i = 0; i < radii.length; i++) {
      sim.spawnJittered(radii[i]!, 30 + i * 8, 90);
    }
    const nowBefore = sim.nowMs;
    sim.settle();
    expect(sim.nowMs).toBe(nowBefore);
    for (const body of sim.bodies) {
      expect(Math.abs(body.vx)).toBeLessThan(HEAP_REST_SPEED);
      expect(Math.abs(body.vy)).toBeLessThan(HEAP_REST_SPEED);
    }
  });
});

describe("heap pile sim conservation", () => {
  it("tracks body count, monotonic ids, and clear semantics", () => {
    const sim = createHeapPileSim({ bin: wideBin(), seed: 1, startMs: 0 });
    const id1 = sim.spawn(6, 50, 50, 0, 0);
    const id2 = sim.spawnJittered(8, 80, 60);
    expect(sim.bodies.length).toBe(2);

    const removed = sim.removeGrabbed(80, 20);
    expect(removed).toBe(id2);
    expect(sim.bodies.length).toBe(1);

    sim.clear();
    expect(sim.bodies.length).toBe(0);

    const id3 = sim.spawn(6, 50, 50, 0, 0);
    expect(id3).toBeGreaterThan(id2);
    expect(id3).not.toBe(id1);

    const jitterAfterClear = sim.spawnJittered(8, 80, 60);
    expect(jitterAfterClear).toBe(id3 + 1);
    expect(sim.bodies.length).toBe(2);
  });
});

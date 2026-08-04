import { describe, expect, it } from "vitest";
import {
  BASE_ORE_PER_DROP,
  DROPS_PER_FACE,
  FACE_BASE_HARDNESS,
  HAUL_ROUND_TRIP_MS,
  HARDNESS_GROWTH,
  OPENING_CARRY_CAPACITY,
  PICK_DAMAGE,
  SMELTER_THROUGHPUT,
  UPGRADE_CARRY_CAPACITY,
  advance,
  advanceWithEvents,
  buyUpgrade,
  carryCapacityFor,
  digRateFor,
  dropDamageFor,
  hardnessFor,
  initialSnapshot,
  nextCarryCapacityUpgradeCost,
  nextDigRateUpgradeCost,
  nextSmelterUpgradeCost,
  oreForDrop,
  smelterThroughputFor,
  type MiningSnapshot,
} from "./mining-engine";
import type { MiningEvent } from "./mining-events";

function snap(partial: Partial<MiningSnapshot> = {}): MiningSnapshot {
  return { ...initialSnapshot(), ...partial };
}

function oreCredited(before: MiningSnapshot, after: MiningSnapshot): number {
  return (
    after.ore -
    before.ore +
    (after.bagOre - before.bagOre) +
    (after.ingots - before.ingots) +
    (after.smelterProgress - before.smelterProgress)
  );
}

describe("mining engine drop constants", () => {
  it("exports drop constants and helpers beside hardnessFor", () => {
    expect(DROPS_PER_FACE).toBe(100);
    expect(BASE_ORE_PER_DROP).toBe(1);
    expect(dropDamageFor(0)).toBe(10);
    expect(oreForDrop(0)).toBe(1);
    expect(dropDamageFor(10)).toBeCloseTo(40.4555773, 6);
    expect(oreForDrop(10)).toBeCloseTo(4.04555773, 7);
  });

  it("keeps Ore per damage flat at 0.1 across Advance", () => {
    const flatOrePerDamage = 0.1;
    for (const advance of [0, 1, 5, 10, 40]) {
      expect(oreForDrop(advance)).toBeCloseTo(
        flatOrePerDamage * dropDamageFor(advance),
        12,
      );
    }
  });
});

describe("mining engine advance", () => {
  it("credits the first Ore drop before the Face breaks", () => {
    const before = snap();
    const after = advance(before, 10_000);
    expect(after.advance).toBe(0);
    expect(oreCredited(before, after)).toBeCloseTo(1, 12);
  });

  it("credits 100 Ore drops across a full Face break", () => {
    const before = snap();
    const after = advance(before, 1_080_000);
    expect(after.advance).toBe(1);
    expect(oreCredited(before, after)).toBeCloseTo(100, 10);
  });

  it("breaks the Face after Hardness damage at Dig Rate 1.0 and yields Ore", () => {
    // 100 drops with Bag / Haul overhead: 10 × (100s mining + 8s haul) = 1_080_000ms.
    const before = snap();
    const after = advance(before, 1_080_000);
    expect(after.advance).toBe(1);
    expect(after.faceSwingProgress).toBe(0);
    expect(oreCredited(before, after)).toBeCloseTo(100, 10);
    expect(after.ingots).toBe(58);
    expect(after.ore).toBeCloseTo(41.44, 2);
    expect(after.smelterProgress).toBeCloseTo(0.56, 2);
  });

  it("does not break the Face before Hardness damage is dealt", () => {
    const almost = advance(snap(), 1_071_999);
    expect(almost.advance).toBe(0);
    expect(almost.faceSwingProgress).toBeCloseTo(999.999, 5);

    const broken = advance(snap(), 1_080_000);
    expect(broken.advance).toBe(1);
  });

  it("is chunk-neutral before the first Face break", () => {
    const once = advance(snap(), 3_000);
    let many = snap();
    for (let i = 0; i < 12; i += 1) {
      many = advance(many, 250);
    }
    expect(many).toEqual(once);
    expect(once.faceSwingProgress).toBe(3);
    expect(once.advance).toBe(0);
  });

  it("is chunk-neutral across a Face break", () => {
    const once = advance(snap(), 3_600_000);
    let many = snap();
    for (let i = 0; i < 3600; i += 1) {
      many = advance(many, 1_000);
    }
    expect(many.advance).toBe(once.advance);
    expect(many.faceSwingProgress).toBeCloseTo(once.faceSwingProgress, 10);
    expect(many.ingots).toBe(once.ingots);
    expect(many.ore).toBeCloseTo(once.ore, 10);
    expect(many.smelterProgress).toBeCloseTo(once.smelterProgress, 10);
  });
});

describe("mining engine Smelter", () => {
  it("drains Ore into smelterProgress at Smelter throughput", () => {
    // 1s: one Swing (no break), Smelter feeds 0.06 from a 10 Ore backlog.
    const after = advance(snap({ ore: 10 }), 1_000);
    expect(after.faceSwingProgress).toBe(1);
    expect(after.ore).toBeCloseTo(10 - SMELTER_THROUGHPUT, 10);
    expect(after.smelterProgress).toBeCloseTo(SMELTER_THROUGHPUT, 10);
    expect(after.ingots).toBe(0);
  });

  it("lets Ore back up when Dig Rate outpaces the Smelter", () => {
    const before = snap();
    const after = advance(before, 216_000);
    expect(after.advance).toBe(0);
    expect(oreCredited(before, after)).toBeGreaterThan(after.ingots - before.ingots);
    expect(after.ore).toBeGreaterThan(0);
  });
});

describe("mining engine Upgrade", () => {
  it("derives Dig Rate and next cost from digRateUpgradeCount", () => {
    expect(digRateFor(0)).toBe(1);
    expect(digRateFor(1)).toBe(1.25);
    expect(nextDigRateUpgradeCost(0)).toBe(5);
    expect(nextDigRateUpgradeCost(1)).toBe(10);
  });

  it("buys an Upgrade when Ingots cover the cost and raises Dig Rate", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich);
    expect(bought.ingots).toBe(0);
    expect(bought.digRateUpgradeCount).toBe(1);
    expect(digRateFor(bought.digRateUpgradeCount)).toBe(1.25);
  });

  it("throws when the Upgrade is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }))).toThrow(/Upgrade/);
  });
});

describe("mining engine offline catch-up", () => {
  it("applies both loops at half rate for the offline window", () => {
    const before = snap();
    const after = advance(before, 2_160_000, { rateScale: 0.5 });
    expect(after.advance).toBe(1);
    expect(oreCredited(before, after)).toBeCloseTo(100, 10);
  });
});

describe("mining engine Hardness curve", () => {
  it("pins opening Face capacity and Pick Damage per economy contract", () => {
    expect(FACE_BASE_HARDNESS).toBe(1000);
    expect(HARDNESS_GROWTH).toBe(1.15);
    expect(PICK_DAMAGE).toBe(1);
  });

  it("maps advance to exponential Hardness per economy contract", () => {
    expect(hardnessFor(0)).toBe(1000);
    expect(hardnessFor(1)).toBe(1150);
    expect(hardnessFor(2)).toBeCloseTo(1322.5, 10);
    expect(hardnessFor(5)).toBeCloseTo(2011.3571875, 10);
    expect(hardnessFor(10)).toBeCloseTo(4045.55773, 4);
  });
});

describe("mining engine Smelter Upgrade", () => {
  it("derives throughput and next cost from smelterUpgradeCount", () => {
    expect(smelterThroughputFor(0)).toBe(0.06);
    expect(smelterThroughputFor(1)).toBe(0.08);
    expect(nextSmelterUpgradeCost(0)).toBe(5);
    expect(nextSmelterUpgradeCost(1)).toBe(10);
  });

  it("initializes smelterUpgradeCount to 0", () => {
    expect(initialSnapshot().smelterUpgradeCount).toBe(0);
  });

  it("buys a Smelter Upgrade when Ingots cover the cost", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich, "smelter");
    expect(bought.ingots).toBe(0);
    expect(bought.smelterUpgradeCount).toBe(1);
    expect(bought.digRateUpgradeCount).toBe(0);
  });

  it("throws when the Smelter Upgrade is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }), "smelter")).toThrow(/Upgrade/);
  });

  it("is chunk-neutral for Smelter drain at upgraded throughput", () => {
    const rich = snap({ ore: 100, smelterUpgradeCount: 1 });
    const once = advance(rich, 2_000);
    let many = rich;
    for (let i = 0; i < 4; i += 1) {
      many = advance(many, 500);
    }
    expect(many.ore).toBeCloseTo(once.ore, 10);
    expect(many.smelterProgress).toBeCloseTo(once.smelterProgress, 10);
    expect(many.ingots).toBe(once.ingots);
  });
});

describe("mining engine buyUpgrade default", () => {
  it("defaults to Dig Rate when upgrade id is omitted", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich);
    expect(bought.digRateUpgradeCount).toBe(1);
    expect(bought.smelterUpgradeCount).toBe(0);
  });
});

describe("mining engine advanceWithEvents", () => {
  it("advance matches advanceWithEvents snapshot", () => {
    const before = snap();
    const options = { rateScale: 0.5 };
    const dtMs = 3_000;
    expect(advance(before, dtMs, options)).toEqual(
      advanceWithEvents(before, dtMs, options).snapshot,
    );
  });

  it("emits swing at 1000 and 2000 ms for Dig Rate 1 over 2500 ms", () => {
    const { events } = advanceWithEvents(snap(), 2_500);
    expect(events).toEqual<MiningEvent[]>([
      { type: "swing", atMs: 1000 },
      { type: "swing", atMs: 2000 },
    ]);
  });

  it("emits swing at 800 and 1600 ms for Dig Rate 1.25 over 2000 ms", () => {
    const { events } = advanceWithEvents(
      snap({ digRateUpgradeCount: 1 }),
      2_000,
    );
    expect(events).toEqual<MiningEvent[]>([
      { type: "swing", atMs: 800 },
      { type: "swing", atMs: 1600 },
    ]);
  });

  it("emits faceBroken at the hardness crossing offset", () => {
    const { events } = advanceWithEvents(snap({ faceSwingProgress: 999 }), 2_000);
    expect(events.filter((e) => e.type === "faceBroken")).toEqual([
      { type: "faceBroken", atMs: 1000 },
    ]);
  });

  it("emits no swing during a Haul", () => {
    const fullBag = advance(snap(), 100_000);
    expect(fullBag.haulRemainingMs).toBeGreaterThan(0);
    const { events } = advanceWithEvents(fullBag, 4_000);
    expect(events.filter((e) => e.type === "swing")).toHaveLength(0);
  });

  it("doubles swing atMs under rateScale 0.5", () => {
    const { events } = advanceWithEvents(snap(), 5_000, { rateScale: 0.5 });
    expect(events).toEqual<MiningEvent[]>([
      { type: "swing", atMs: 2000 },
      { type: "swing", atMs: 4000 },
    ]);
  });

  it("emits faceBroken without swing for discarded partial at break", () => {
    const almostBroken = snap({ faceSwingProgress: 999 });
    const { events, snapshot } = advanceWithEvents(almostBroken, 2_000);
    expect(events).toEqual<MiningEvent[]>([
      { type: "faceBroken", atMs: 1000 },
      { type: "swing", atMs: 2000 },
    ]);
    expect(snapshot.advance).toBe(1);
    expect(snapshot.faceSwingProgress).toBe(1);
  });

  it("is chunk-neutral for events over 2500 ms", () => {
    const once = advanceWithEvents(snap(), 2_500);
    let manyEvents: MiningEvent[] = [];
    let cursor = snap();
    for (let i = 0; i < 10; i += 1) {
      const step = advanceWithEvents(cursor, 250);
      manyEvents = manyEvents.concat(
        step.events.map((e) => ({ ...e, atMs: e.atMs + i * 250 })),
      );
      cursor = step.snapshot;
    }
    expect(manyEvents).toEqual(once.events);
  });
});

describe("mining engine Bag and Haul", () => {
  it("initializes Bag fields and SCHEMA_VERSION 3 to zero", () => {
    const s = initialSnapshot();
    expect(s.schemaVersion).toBe(3);
    expect(s.bagOre).toBe(0);
    expect(s.bagLoads).toBe(0);
    expect(s.haulRemainingMs).toBe(0);
    expect(s.carryCapacityUpgradeCount).toBe(0);
  });

  it("exports Carry Capacity ladder constants and helpers", () => {
    expect(OPENING_CARRY_CAPACITY).toBe(10);
    expect(UPGRADE_CARRY_CAPACITY).toBe(5);
    expect(HAUL_ROUND_TRIP_MS).toBe(8000);
    expect(carryCapacityFor(0)).toBe(10);
    expect(carryCapacityFor(1)).toBe(15);
    expect(nextCarryCapacityUpgradeCost(0)).toBe(5);
    expect(nextCarryCapacityUpgradeCost(1)).toBe(10);
  });

  it("buys a Carry Capacity Upgrade when Ingots cover the cost", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich, "carryCapacity");
    expect(bought.ingots).toBe(0);
    expect(bought.carryCapacityUpgradeCount).toBe(1);
    expect(carryCapacityFor(bought.carryCapacityUpgradeCount)).toBe(15);
  });

  it("throws when the Carry Capacity Upgrade is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }), "carryCapacity")).toThrow(
      /Upgrade/,
    );
  });

  it("credits drops to the Bag, not Colony ore", () => {
    const before = snap();
    const after = advance(before, 10_000);
    expect(after.ore).toBe(0);
    expect(after.bagOre).toBe(1);
    expect(after.bagLoads).toBe(1);
  });

  it("suspends mining when the Bag is full and delivers at the Haul midpoint", () => {
    const atTenthDrop = advance(snap(), 100_000);
    expect(atTenthDrop.bagLoads).toBe(10);
    expect(atTenthDrop.ore).toBe(0);
    expect(atTenthDrop.haulRemainingMs).toBeGreaterThan(0);

    const atDelivery = advance(snap(), 104_000);
    expect(atDelivery.ore).toBe(10);
    expect(atDelivery.bagLoads).toBe(0);
    expect(atDelivery.bagOre).toBe(0);
    expect(atDelivery.haulRemainingMs).toBeGreaterThan(0);

    const haulComplete = advance(snap(), 108_000);
    expect(haulComplete.haulRemainingMs).toBe(0);
    expect(haulComplete.faceSwingProgress).toBeGreaterThan(0);
  });

  it("spends 1_000_000 ms mining and 80_000 ms hauling over 1_080_000 ms", () => {
    const end = advance(snap(), 1_080_000);
    expect(end.advance).toBe(1);
    expect(end.faceSwingProgress).toBe(0);
    expect(oreCredited(snap(), end)).toBeCloseTo(100, 10);
    let haulingMs = 0;
    let snapshot = snap();
    for (let t = 0; t < 1_080_000; t += 1_000) {
      if (snapshot.haulRemainingMs > 0) {
        haulingMs += 1_000;
      }
      snapshot = advance(snapshot, 1_000);
    }
    expect(haulingMs).toBe(80_000);
    expect(1_080_000 - haulingMs).toBe(1_000_000);
  });

  it("scales the Haul countdown with rateScale like Dig Rate", () => {
    const half = advance(snap(), 28_800_000, { rateScale: 0.5 });
    const full = advance(snap(), 14_400_000);
    expect(half).toEqual(full);
  });

  it("is chunk-neutral across a Haul", () => {
    const once = advance(snap(), 1_080_000);
    let many = snap();
    for (let i = 0; i < 1080; i += 1) {
      many = advance(many, 1_000);
    }
    expect(many.advance).toBe(once.advance);
    expect(many.faceSwingProgress).toBeCloseTo(once.faceSwingProgress, 10);
    expect(many.bagOre).toBeCloseTo(once.bagOre, 10);
    expect(many.bagLoads).toBe(once.bagLoads);
    expect(many.haulRemainingMs).toBe(once.haulRemainingMs);
    expect(many.ore).toBeCloseTo(once.ore, 10);
    expect(many.ingots).toBe(once.ingots);
    expect(many.smelterProgress).toBeCloseTo(once.smelterProgress, 10);
  });
});

import { describe, expect, it } from "vitest";
import {
  BASE_ORE_PER_DROP,
  DROPS_PER_FACE,
  FACE_BASE_HARDNESS,
  HAUL_ROUND_TRIP_MS,
  HARDNESS_GROWTH,
  OPENING_CARRY_CAPACITY,
  nextPickDamageUpgradeCost,
  pickDamageFor,
  SMELTER_THROUGHPUT,
  UPGRADE_CARRY_CAPACITY,
  advance,
  advanceWithEvents,
  buyUpgrade,
  carryCapacityFor,
  digRateFor,
  dropDamageFor,
  hardnessFor,
  haulSpeedFor,
  heapCapacityFor,
  HIRE_HAULER_COST,
  initialSnapshot,
  nextCarryCapacityUpgradeCost,
  nextDigRateUpgradeCost,
  nextHaulSpeedUpgradeCost,
  nextSmelterUpgradeCost,
  OFFLINE_RATE_SCALE,
  oreForDrop,
  pickupMsPerLoad,
  PICKUP_MS_PER_LOAD,
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

describe("mining engine Pick Damage Upgrade", () => {
  it("derives Pick Damage and next cost from pickDamageUpgradeCount", () => {
    expect(pickDamageFor(0)).toBe(1);
    expect(pickDamageFor(1)).toBe(1.5);
    expect(pickDamageFor(2)).toBe(2.25);
    expect(pickDamageFor(3)).toBe(3.375);
    expect(pickDamageFor(4)).toBe(5.0625);
    expect(nextPickDamageUpgradeCost(0)).toBe(5);
    expect(nextPickDamageUpgradeCost(1)).toBe(10);
    expect(nextPickDamageUpgradeCost(2)).toBe(20);
    expect(nextPickDamageUpgradeCost(3)).toBe(40);
    expect(nextPickDamageUpgradeCost(4)).toBe(80);
  });

  it("initializes pickDamageUpgradeCount to 0", () => {
    expect(initialSnapshot().pickDamageUpgradeCount).toBe(0);
  });

  it("preserves pickDamageUpgradeCount across advanceWithEvents", () => {
    const before = snap({ pickDamageUpgradeCount: 3 });
    const { snapshot: after } = advanceWithEvents(before, 1_000);
    expect(after.pickDamageUpgradeCount).toBe(3);
  });

  it("multiplies damage per second by Pick Damage at equal Dig Rate", () => {
    const dtMs = 10_000;
    const at0 = advance(snap({ pickDamageUpgradeCount: 0 }), dtMs);
    const at2 = advance(snap({ pickDamageUpgradeCount: 2 }), dtMs);
    expect(at2.faceSwingProgress).toBeCloseTo(at0.faceSwingProgress * 2.25, 10);
  });

  it("buys a Pick Damage Upgrade when Ingots cover the cost", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich, "pickDamage");
    expect(bought.ingots).toBe(0);
    expect(bought.pickDamageUpgradeCount).toBe(1);
    expect(pickDamageFor(bought.pickDamageUpgradeCount)).toBe(1.5);
  });

  it("throws when the Pick Damage Upgrade is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }), "pickDamage")).toThrow(/Upgrade/);
  });
});

describe("mining engine Hardness curve", () => {
  it("pins opening Face capacity per economy contract", () => {
    expect(FACE_BASE_HARDNESS).toBe(1000);
    expect(HARDNESS_GROWTH).toBe(1.15);
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

describe("mining engine Haul Speed and Hire Hauler upgrades", () => {
  it("buys Haul Speed when Ingots cover the cost", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich, "haulSpeed");
    expect(bought.ingots).toBe(0);
    expect(bought.haulSpeedUpgradeCount).toBe(1);
    expect(haulSpeedFor(bought.haulSpeedUpgradeCount)).toBe(1.25);
  });

  it("throws when Haul Speed is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }), "haulSpeed")).toThrow(/Upgrade/);
  });

  it("hires the Hauler when Ingots cover the cost", () => {
    const rich = snap({ ingots: 160 });
    const bought = buyUpgrade(rich, "hireHauler");
    expect(bought.ingots).toBe(0);
    expect(bought.crewSize).toBe(2);
  });

  it("throws when Hire Hauler is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 159 }), "hireHauler")).toThrow(
      /Upgrade/,
    );
  });

  it("throws when the Hauler is already hired", () => {
    expect(() => buyUpgrade(snap({ crewSize: 2, ingots: 200 }), "hireHauler")).toThrow(
      /Hauler/,
    );
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
  it("live advance snapshot is unchanged when events are collected", () => {
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

  it("emits loadDropped at 10000 ms for the first Ore drop at Dig Rate 1", () => {
    const dropDamage = dropDamageFor(0);
    const digRate = digRateFor(0);
    const firstDropAtMs = (dropDamage / digRate) * 1000;
    expect(firstDropAtMs).toBe(10_000);

    const { events } = advanceWithEvents(snap(), firstDropAtMs);
    expect(events.filter((e) => e.type === "loadDropped")).toEqual([
      { type: "loadDropped", atMs: firstDropAtMs },
    ]);
  });

  it("emits loadDropped at the first Ore drop with a two-Dwarf Crew", () => {
    const dropDamage = dropDamageFor(0);
    const digRate = digRateFor(0);
    const firstDropAtMs = (dropDamage / digRate) * 1000;

    const { events } = advanceWithEvents(snap({ crewSize: 2 }), firstDropAtMs);
    expect(events.filter((e) => e.type === "loadDropped")).toEqual([
      { type: "loadDropped", atMs: firstDropAtMs },
    ]);
  });

  it("emits one loadDropped for every credited Ore drop", () => {
    const before = snap();
    const dtMs = 100_000;
    const { events, snapshot } = advanceWithEvents(before, dtMs);
    const dropEvents = events.filter((e) => e.type === "loadDropped");
    expect(dropEvents).toHaveLength(snapshot.bagLoads - before.bagLoads);
  });

  it("returns events sorted by non-decreasing atMs", () => {
    const { events } = advanceWithEvents(snap(), 100_000);
    for (let i = 1; i < events.length; i += 1) {
      expect(events[i]!.atMs).toBeGreaterThanOrEqual(events[i - 1]!.atMs);
    }
  });

  it("is chunk-neutral for loadDropped events live and offline", () => {
    for (const rateScale of [1, OFFLINE_RATE_SCALE] as const) {
      const dtMs = 25_000;
      const stepMs = 250;
      const once = advanceWithEvents(snap(), dtMs, { rateScale });
      const loadDroppedOnce = once.events.filter((e) => e.type === "loadDropped");

      let loadDroppedMany: MiningEvent[] = [];
      let cursor = snap();
      for (let i = 0; i < dtMs / stepMs; i += 1) {
        const step = advanceWithEvents(cursor, stepMs, { rateScale });
        loadDroppedMany = loadDroppedMany.concat(
          step.events
            .filter((e) => e.type === "loadDropped")
            .map((e) => ({ ...e, atMs: e.atMs + i * stepMs })),
        );
        cursor = step.snapshot;
      }
      expect(loadDroppedMany).toEqual(loadDroppedOnce);
    }
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
      { type: "loadDropped", atMs: 1000 },
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

  const ONE_DWARF_200S_SNAPSHOT = {
    schemaVersion: 5 as const,
    advance: 0,
    ore: 4.240000000000003,
    ingots: 5,
    digRateUpgradeCount: 0,
    pickDamageUpgradeCount: 0,
    smelterUpgradeCount: 0,
    carryCapacityUpgradeCount: 0,
    crewSize: 1,
    heapLoads: 0,
    heapOre: 0,
    haulSpeedUpgradeCount: 0,
    pickupProgressMs: 0,
    faceSwingProgress: 192,
    smelterProgress: 0.7599999999999998,
    bagOre: 9,
    bagLoads: 9,
    haulRemainingMs: 0,
  };

  const ONE_DWARF_200S_EVENTS: MiningEvent[] = [
    { type: "swing", atMs: 1000 },
    { type: "swing", atMs: 2000 },
    { type: "swing", atMs: 3000 },
    { type: "swing", atMs: 4000 },
    { type: "swing", atMs: 5000 },
    { type: "swing", atMs: 6000 },
    { type: "swing", atMs: 7000 },
    { type: "swing", atMs: 8000 },
    { type: "swing", atMs: 9000 },
    { type: "swing", atMs: 10000 },
    { type: "loadDropped", atMs: 10000 },
    { type: "swing", atMs: 11000 },
    { type: "swing", atMs: 12000 },
    { type: "swing", atMs: 13000 },
    { type: "swing", atMs: 14000 },
    { type: "swing", atMs: 15000 },
    { type: "swing", atMs: 16000 },
    { type: "swing", atMs: 17000 },
    { type: "swing", atMs: 18000 },
    { type: "swing", atMs: 19000 },
    { type: "swing", atMs: 20000 },
    { type: "loadDropped", atMs: 20000 },
    { type: "swing", atMs: 21000 },
    { type: "swing", atMs: 22000 },
    { type: "swing", atMs: 23000 },
    { type: "swing", atMs: 24000 },
    { type: "swing", atMs: 25000 },
    { type: "swing", atMs: 26000 },
    { type: "swing", atMs: 27000 },
    { type: "swing", atMs: 28000 },
    { type: "swing", atMs: 29000 },
    { type: "swing", atMs: 30000 },
    { type: "loadDropped", atMs: 30000 },
    { type: "swing", atMs: 31000 },
    { type: "swing", atMs: 32000 },
    { type: "swing", atMs: 33000 },
    { type: "swing", atMs: 34000 },
    { type: "swing", atMs: 35000 },
    { type: "swing", atMs: 36000 },
    { type: "swing", atMs: 37000 },
    { type: "swing", atMs: 38000 },
    { type: "swing", atMs: 39000 },
    { type: "swing", atMs: 40000 },
    { type: "loadDropped", atMs: 40000 },
    { type: "swing", atMs: 41000 },
    { type: "swing", atMs: 42000 },
    { type: "swing", atMs: 43000 },
    { type: "swing", atMs: 44000 },
    { type: "swing", atMs: 45000 },
    { type: "swing", atMs: 46000 },
    { type: "swing", atMs: 47000 },
    { type: "swing", atMs: 48000 },
    { type: "swing", atMs: 49000 },
    { type: "swing", atMs: 50000 },
    { type: "loadDropped", atMs: 50000 },
    { type: "swing", atMs: 51000 },
    { type: "swing", atMs: 52000 },
    { type: "swing", atMs: 53000 },
    { type: "swing", atMs: 54000 },
    { type: "swing", atMs: 55000 },
    { type: "swing", atMs: 56000 },
    { type: "swing", atMs: 57000 },
    { type: "swing", atMs: 58000 },
    { type: "swing", atMs: 59000 },
    { type: "swing", atMs: 60000 },
    { type: "loadDropped", atMs: 60000 },
    { type: "swing", atMs: 61000 },
    { type: "swing", atMs: 62000 },
    { type: "swing", atMs: 63000 },
    { type: "swing", atMs: 64000 },
    { type: "swing", atMs: 65000 },
    { type: "swing", atMs: 66000 },
    { type: "swing", atMs: 67000 },
    { type: "swing", atMs: 68000 },
    { type: "swing", atMs: 69000 },
    { type: "swing", atMs: 70000 },
    { type: "loadDropped", atMs: 70000 },
    { type: "swing", atMs: 71000 },
    { type: "swing", atMs: 72000 },
    { type: "swing", atMs: 73000 },
    { type: "swing", atMs: 74000 },
    { type: "swing", atMs: 75000 },
    { type: "swing", atMs: 76000 },
    { type: "swing", atMs: 77000 },
    { type: "swing", atMs: 78000 },
    { type: "swing", atMs: 79000 },
    { type: "swing", atMs: 80000 },
    { type: "loadDropped", atMs: 80000 },
    { type: "swing", atMs: 81000 },
    { type: "swing", atMs: 82000 },
    { type: "swing", atMs: 83000 },
    { type: "swing", atMs: 84000 },
    { type: "swing", atMs: 85000 },
    { type: "swing", atMs: 86000 },
    { type: "swing", atMs: 87000 },
    { type: "swing", atMs: 88000 },
    { type: "swing", atMs: 89000 },
    { type: "swing", atMs: 90000 },
    { type: "loadDropped", atMs: 90000 },
    { type: "swing", atMs: 91000 },
    { type: "swing", atMs: 92000 },
    { type: "swing", atMs: 93000 },
    { type: "swing", atMs: 94000 },
    { type: "swing", atMs: 95000 },
    { type: "swing", atMs: 96000 },
    { type: "swing", atMs: 97000 },
    { type: "swing", atMs: 98000 },
    { type: "swing", atMs: 99000 },
    { type: "swing", atMs: 100000 },
    { type: "loadDropped", atMs: 100000 },
    { type: "swing", atMs: 109000 },
    { type: "swing", atMs: 110000 },
    { type: "swing", atMs: 111000 },
    { type: "swing", atMs: 112000 },
    { type: "swing", atMs: 113000 },
    { type: "swing", atMs: 114000 },
    { type: "swing", atMs: 115000 },
    { type: "swing", atMs: 116000 },
    { type: "swing", atMs: 117000 },
    { type: "swing", atMs: 118000 },
    { type: "loadDropped", atMs: 118000 },
    { type: "swing", atMs: 119000 },
    { type: "swing", atMs: 120000 },
    { type: "swing", atMs: 121000 },
    { type: "swing", atMs: 122000 },
    { type: "swing", atMs: 123000 },
    { type: "swing", atMs: 124000 },
    { type: "swing", atMs: 125000 },
    { type: "swing", atMs: 126000 },
    { type: "swing", atMs: 127000 },
    { type: "swing", atMs: 128000 },
    { type: "loadDropped", atMs: 128000 },
    { type: "swing", atMs: 129000 },
    { type: "swing", atMs: 130000 },
    { type: "swing", atMs: 131000 },
    { type: "swing", atMs: 132000 },
    { type: "swing", atMs: 133000 },
    { type: "swing", atMs: 134000 },
    { type: "swing", atMs: 135000 },
    { type: "swing", atMs: 136000 },
    { type: "swing", atMs: 137000 },
    { type: "swing", atMs: 138000 },
    { type: "loadDropped", atMs: 138000 },
    { type: "swing", atMs: 139000 },
    { type: "swing", atMs: 140000 },
    { type: "swing", atMs: 141000 },
    { type: "swing", atMs: 142000 },
    { type: "swing", atMs: 143000 },
    { type: "swing", atMs: 144000 },
    { type: "swing", atMs: 145000 },
    { type: "swing", atMs: 146000 },
    { type: "swing", atMs: 147000 },
    { type: "swing", atMs: 148000 },
    { type: "loadDropped", atMs: 148000 },
    { type: "swing", atMs: 149000 },
    { type: "swing", atMs: 150000 },
    { type: "swing", atMs: 151000 },
    { type: "swing", atMs: 152000 },
    { type: "swing", atMs: 153000 },
    { type: "swing", atMs: 154000 },
    { type: "swing", atMs: 155000 },
    { type: "swing", atMs: 156000 },
    { type: "swing", atMs: 157000 },
    { type: "swing", atMs: 158000 },
    { type: "loadDropped", atMs: 158000 },
    { type: "swing", atMs: 159000 },
    { type: "swing", atMs: 160000 },
    { type: "swing", atMs: 161000 },
    { type: "swing", atMs: 162000 },
    { type: "swing", atMs: 163000 },
    { type: "swing", atMs: 164000 },
    { type: "swing", atMs: 165000 },
    { type: "swing", atMs: 166000 },
    { type: "swing", atMs: 167000 },
    { type: "swing", atMs: 168000 },
    { type: "loadDropped", atMs: 168000 },
    { type: "swing", atMs: 169000 },
    { type: "swing", atMs: 170000 },
    { type: "swing", atMs: 171000 },
    { type: "swing", atMs: 172000 },
    { type: "swing", atMs: 173000 },
    { type: "swing", atMs: 174000 },
    { type: "swing", atMs: 175000 },
    { type: "swing", atMs: 176000 },
    { type: "swing", atMs: 177000 },
    { type: "swing", atMs: 178000 },
    { type: "loadDropped", atMs: 178000 },
    { type: "swing", atMs: 179000 },
    { type: "swing", atMs: 180000 },
    { type: "swing", atMs: 181000 },
    { type: "swing", atMs: 182000 },
    { type: "swing", atMs: 183000 },
    { type: "swing", atMs: 184000 },
    { type: "swing", atMs: 185000 },
    { type: "swing", atMs: 186000 },
    { type: "swing", atMs: 187000 },
    { type: "swing", atMs: 188000 },
    { type: "loadDropped", atMs: 188000 },
    { type: "swing", atMs: 189000 },
    { type: "swing", atMs: 190000 },
    { type: "swing", atMs: 191000 },
    { type: "swing", atMs: 192000 },
    { type: "swing", atMs: 193000 },
    { type: "swing", atMs: 194000 },
    { type: "swing", atMs: 195000 },
    { type: "swing", atMs: 196000 },
    { type: "swing", atMs: 197000 },
    { type: "swing", atMs: 198000 },
    { type: "loadDropped", atMs: 198000 },
    { type: "swing", atMs: 199000 },
    { type: "swing", atMs: 200000 },
  ];

  it("keeps one-Dwarf Crew advance identical to pre-slice behavior at 200s", () => {
    const result = advanceWithEvents(snap({ crewSize: 1 }), 200_000);
    expect(result.snapshot).toEqual(ONE_DWARF_200S_SNAPSHOT);
    expect(result.events).toEqual(ONE_DWARF_200S_EVENTS);
  });

  it("drops Ore into the Heap with a two-Dwarf Crew", () => {
    const after = advance(snap({ crewSize: 2 }), 10_000);
    expect(after.heapLoads).toBe(1);
    expect(after.bagLoads).toBe(0);
    expect(after.heapOre).toBe(1);
  });

  it("stalls the Miner when the Heap is full", () => {
    const before = snap({
      crewSize: 2,
      heapLoads: 10,
      heapOre: 10,
      bagLoads: 10,
      bagOre: 10,
      haulRemainingMs: 100_000,
    });
    const { snapshot, events } = advanceWithEvents(before, 100_000);
    expect(snapshot.heapLoads).toBe(10);
    expect(snapshot.faceSwingProgress).toBe(before.faceSwingProgress);
    expect(events.filter((e) => e.type === "swing")).toHaveLength(0);
  });

  it("picks up one Load from the Heap at pickupMsPerLoad", () => {
    const almost = advance(snap({ crewSize: 2, heapLoads: 1, heapOre: 1 }), 9_999);
    expect(almost.bagLoads).toBe(0);
    expect(almost.heapLoads).toBe(1);

    const picked = advance(
      snap({ crewSize: 2, heapLoads: 1, heapOre: 1, pickupProgressMs: 9_999 }),
      1,
    );
    expect(picked.bagLoads).toBe(1);
    expect(picked.heapLoads).toBe(0);
    expect(picked.bagOre).toBe(1);
    expect(picked.heapOre).toBe(0);
    expect(picked.pickupProgressMs).toBe(0);
  });

  it("departs only when the Hauler's Bag is full", () => {
    const at99s = advance(
      snap({ crewSize: 2, heapLoads: 10, heapOre: 10, bagLoads: 0 }),
      99_999,
    );
    expect(at99s.haulRemainingMs).toBe(0);
    expect(at99s.bagLoads).toBe(9);

    const at100s = advance(
      snap({ crewSize: 2, heapLoads: 10, heapOre: 10, bagLoads: 0 }),
      100_000,
    );
    expect(at100s.haulRemainingMs).toBe(HAUL_ROUND_TRIP_MS);
    expect(at100s.bagLoads).toBe(10);
  });

  it("keeps the Miner swinging during a two-Dwarf Haul", () => {
    const midHaul = snap({
      crewSize: 2,
      heapLoads: 0,
      heapOre: 0,
      bagLoads: 10,
      bagOre: 10,
      haulRemainingMs: HAUL_ROUND_TRIP_MS,
    });
    const { snapshot, events } = advanceWithEvents(midHaul, 5_000);
    expect(snapshot.haulRemainingMs).toBeGreaterThan(0);
    expect(snapshot.faceSwingProgress).toBe(5);
    expect(events.filter((e) => e.type === "swing")).toEqual([
      { type: "swing", atMs: 1000 },
      { type: "swing", atMs: 2000 },
      { type: "swing", atMs: 3000 },
      { type: "swing", atMs: 4000 },
      { type: "swing", atMs: 5000 },
    ]);
  });

  it("orders event atMs across drop, pickup, and Bag-full boundaries", () => {
    const { events } = advanceWithEvents(
      snap({ crewSize: 2, heapLoads: 9, heapOre: 9 }),
      110_000,
    );
    const atMs = events.map((e) => e.atMs);
    for (let i = 1; i < atMs.length; i += 1) {
      expect(atMs[i]).toBeGreaterThanOrEqual(atMs[i - 1]!);
    }
    expect(events.some((e) => e.type === "swing")).toBe(true);
    expect(atMs).toContain(100_000);
  });

  it("is chunk-neutral for a two-Dwarf Crew", () => {
    const once = advance(snap({ crewSize: 2 }), 60_000);
    let many = snap({ crewSize: 2 });
    for (let i = 0; i < 240; i += 1) {
      many = advance(many, 250);
    }
    expect(many).toEqual(once);
  });
});

describe("mining engine Crew and Heap", () => {
  it("initializes Crew, Heap, and pickup fields on a fresh Snapshot", () => {
    const s = initialSnapshot();
    expect(s.crewSize).toBe(1);
    expect(s.heapLoads).toBe(0);
    expect(s.heapOre).toBe(0);
    expect(s.haulSpeedUpgradeCount).toBe(0);
    expect(s.pickupProgressMs).toBe(0);
  });

  it("exports pickup constants and derived helpers with worked values", () => {
    expect(PICKUP_MS_PER_LOAD).toBe(10_000);
    expect(HIRE_HAULER_COST).toBe(160);
    expect(haulSpeedFor(0)).toBe(1);
    expect(haulSpeedFor(1)).toBe(1.25);
    expect(haulSpeedFor(4)).toBe(2);
    expect(pickupMsPerLoad(0)).toBe(10_000);
    expect(pickupMsPerLoad(1)).toBe(8_000);
    expect(nextHaulSpeedUpgradeCost(0)).toBe(5);
    expect(nextHaulSpeedUpgradeCost(3)).toBe(40);
    expect(heapCapacityFor(0)).toBe(10);
  });
});

describe("mining engine Bag and Haul", () => {
  it("initializes Bag fields and sets SCHEMA_VERSION to 5", () => {
    const s = initialSnapshot();
    expect(s.schemaVersion).toBe(5);
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

import { describe, expect, it } from "vitest";
import {
  BASE_ORE_PER_DROP,
  DROPS_PER_FACE,
  FACE_BASE_HARDNESS,
  HARDNESS_GROWTH,
  PICK_DAMAGE,
  SMELTER_THROUGHPUT,
  advance,
  buyUpgrade,
  digRateFor,
  dropDamageFor,
  hardnessFor,
  initialSnapshot,
  nextDigRateUpgradeCost,
  nextSmelterUpgradeCost,
  oreForDrop,
  smelterThroughputFor,
  type MiningSnapshot,
} from "./mining-engine";

function snap(partial: Partial<MiningSnapshot> = {}): MiningSnapshot {
  return { ...initialSnapshot(), ...partial };
}

function oreCredited(before: MiningSnapshot, after: MiningSnapshot): number {
  return (
    after.ore -
    before.ore +
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
    const after = advance(before, 1_000_000);
    expect(after.advance).toBe(1);
    expect(oreCredited(before, after)).toBeCloseTo(100, 10);
  });

  it("breaks the Face after Hardness damage at Dig Rate 1.0 and yields Ore", () => {
    // Opening Dig Rate 1.0 Swing/sec × Hardness 1000 → break at 1_000_000ms; 100 drops.
    const before = snap();
    const after = advance(before, 1_000_000);
    expect(after.advance).toBe(1);
    expect(after.faceSwingProgress).toBe(0);
    expect(oreCredited(before, after)).toBeCloseTo(100, 10);
    expect(after.ingots).toBe(59);
    expect(after.ore).toBeCloseTo(40.6, 10);
    expect(after.smelterProgress).toBeCloseTo(0.4, 10);
  });

  it("does not break the Face before Hardness damage is dealt", () => {
    const almost = advance(snap(), 999_999);
    expect(almost.advance).toBe(0);
    expect(almost.faceSwingProgress).toBeCloseTo(999.999, 5);

    const broken = advance(snap(), 1_000_000);
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
    const after = advance(before, 100_000);
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
    const after = advance(before, 2_000_000, { rateScale: 0.5 });
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

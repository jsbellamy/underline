import { describe, expect, it } from "vitest";
import {
  HARDNESS,
  SMELTER_THROUGHPUT,
  YIELD,
  advance,
  buyUpgrade,
  digRateFor,
  hardnessFor,
  initialSnapshot,
  nextUpgradeCost,
  nextSmelterUpgradeCost,
  smelterThroughputFor,
  type MiningSnapshot,
} from "./mining-engine";

function snap(partial: Partial<MiningSnapshot> = {}): MiningSnapshot {
  return { ...initialSnapshot(), ...partial };
}

describe("mining engine advance", () => {
  it("breaks the Face after Hardness Swings at Dig Rate 1.0 and yields Ore", () => {
    // Opening Dig Rate 1.0 Swing/sec × Hardness 4 → break at 4000ms; Yield 1.
    // Then Smelter drains 0.15×4s = 0.6 Ore into progress.
    const after = advance(snap(), 4_000);
    expect(after.advance).toBe(1);
    expect(after.ore).toBeCloseTo(YIELD - SMELTER_THROUGHPUT * 4, 10);
    expect(after.faceSwingProgress).toBe(0);
    expect(after.smelterProgress).toBeCloseTo(SMELTER_THROUGHPUT * 4, 10);
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
});

describe("mining engine Smelter", () => {
  it("drains Ore into smelterProgress at Smelter throughput", () => {
    // 1s: one Swing (no break), Smelter feeds 0.15 from a 10 Ore backlog.
    const after = advance(snap({ ore: 10 }), 1_000);
    expect(after.faceSwingProgress).toBe(1);
    expect(after.ore).toBeCloseTo(10 - SMELTER_THROUGHPUT, 10);
    expect(after.smelterProgress).toBeCloseTo(SMELTER_THROUGHPUT, 10);
    expect(after.ingots).toBe(0);
  });

  it("lets Ore back up when Dig Rate outpaces the Smelter", () => {
    // Dig-all then Smelter-drain (engine contract): 16s → 4 breaks → +4 Ore;
    // Smelter takes 0.15×16 = 2.4 → 2 Ingots, backlog 1.6, progress 0.4.
    const after = advance(snap(), 16_000);
    expect(after.advance).toBe(4);
    expect(after.ingots).toBe(2);
    expect(after.ore).toBeCloseTo(1.6, 10);
    expect(after.smelterProgress).toBeCloseTo(0.4, 10);
  });
});

describe("mining engine Upgrade", () => {
  it("derives Dig Rate and next cost from upgradeCount", () => {
    expect(digRateFor(0)).toBe(1);
    expect(digRateFor(1)).toBe(1.25);
    expect(nextUpgradeCost(0)).toBe(5);
    expect(nextUpgradeCost(1)).toBe(10);
  });

  it("buys an Upgrade when Ingots cover the cost and raises Dig Rate", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich);
    expect(bought.ingots).toBe(0);
    expect(bought.upgradeCount).toBe(1);
    expect(digRateFor(bought.upgradeCount)).toBe(1.25);
  });

  it("throws when the Upgrade is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }))).toThrow(/Upgrade/);
  });
});

describe("mining engine offline catch-up", () => {
  it("applies both loops at half rate for the offline window", () => {
    // 8s offline at 50% ≡ 4s live: one Face break; Smelter 0.15×4 = 0.6.
    const after = advance(snap(), 8_000, { rateScale: 0.5 });
    expect(after.advance).toBe(1);
    expect(after.ore).toBeCloseTo(0.4, 10);
    expect(after.ingots).toBe(0);
    expect(after.smelterProgress).toBeCloseTo(0.6, 10);
  });
});

describe("mining engine Hardness constant", () => {
  it("keeps Hardness at 4 Swings per Mineable Block", () => {
    expect(HARDNESS).toBe(4);
  });
});

describe("mining engine Hardness bands", () => {
  it("maps advance to banded Hardness per economy contract", () => {
    expect(hardnessFor(0)).toBe(4);
    expect(hardnessFor(24)).toBe(4);
    expect(hardnessFor(25)).toBe(5);
    expect(hardnessFor(74)).toBe(5);
    expect(hardnessFor(75)).toBe(6);
    expect(hardnessFor(149)).toBe(6);
    expect(hardnessFor(150)).toBe(7);
    expect(hardnessFor(999)).toBe(7);
  });
});

describe("mining engine Smelter Upgrade", () => {
  it("derives throughput and next cost from smelterUpgradeCount", () => {
    expect(smelterThroughputFor(0)).toBe(0.15);
    expect(smelterThroughputFor(1)).toBe(0.2);
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
    expect(bought.upgradeCount).toBe(0);
    expect(smelterThroughputFor(bought.smelterUpgradeCount ?? 0)).toBe(0.2);
  });

  it("throws when the Smelter Upgrade is unaffordable", () => {
    expect(() => buyUpgrade(snap({ ingots: 4 }), "smelter")).toThrow(/Upgrade/);
  });
});

describe("mining engine buyUpgrade default", () => {
  it("defaults to Dig Rate when upgrade id is omitted", () => {
    const rich = snap({ ingots: 5 });
    const bought = buyUpgrade(rich);
    expect(bought.upgradeCount).toBe(1);
    expect(bought.smelterUpgradeCount).toBe(0);
  });
});

describe("mining engine multi-break Hardness bands", () => {
  it("uses rising Hardness as advance crosses band boundaries in one window", () => {
    // advance 24 → hardness 4; break → 25 → hardness 5 for the next Face.
    const atBandEdge = snap({ advance: 24, faceSwingProgress: 3 });
    const afterOneBreak = advance(atBandEdge, 1_000);
    expect(afterOneBreak.advance).toBe(25);
    expect(afterOneBreak.faceSwingProgress).toBe(0);

    // One more second at Dig Rate 1.0 needs 5 Swings to break at hardness 5.
    const afterSecondBreak = advance(afterOneBreak, 5_000);
    expect(afterSecondBreak.advance).toBe(26);
    expect(afterSecondBreak.faceSwingProgress).toBe(0);
  });
});

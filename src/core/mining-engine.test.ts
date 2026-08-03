import { describe, expect, it } from "vitest";
import {
  HARDNESS,
  SMELTER_THROUGHPUT,
  YIELD,
  advance,
  buyUpgrade,
  digRateFor,
  initialSnapshot,
  nextUpgradeCost,
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

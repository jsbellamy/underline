import { describe, expect, it } from "vitest";
import {
  OFFLINE_RATE_SCALE,
  SCHEMA_VERSION,
  advance,
  initialSnapshot,
} from "./mining-engine";
import {
  buildOfflineSummary,
  toWireSnapshot,
  wireSnapshotChanged,
} from "./wire-snapshot";

describe("wire Snapshot", () => {
  it("projects save-authoritative fields for the Dock", () => {
    const snap = {
      ...initialSnapshot(),
      advance: 2,
      ore: 1.25,
      ingots: 3,
      digRateUpgradeCount: 1,
      crewSize: 2,
      heapLoads: 3,
      heapOre: 7,
      haulSpeedUpgradeCount: 2,
      pickupProgressMs: 4_200,
      faceSwingProgress: 2,
      smelterProgress: 0.3,
    };
    const wire = toWireSnapshot(snap);
    expect(wire).toEqual({
      schemaVersion: SCHEMA_VERSION,
      advance: 2,
      ore: 1.25,
      ingots: 3,
      digRateUpgradeCount: 1,
      pickDamageUpgradeCount: 0,
      smelterUpgradeCount: 0,
      carryCapacityUpgradeCount: 0,
      crewSize: 2,
      heapLoads: 3,
      heapOre: 7,
      haulSpeedUpgradeCount: 2,
      grabSizeUpgradeCount: 0,
      unloadSpeedUpgradeCount: 0,
      faceSwingProgress: 2,
      smelterProgress: 0.3,
      bagOre: 0,
      bagLoads: 0,
      haulRemainingMs: 0,
    });
    expect(wire).not.toHaveProperty("pickupProgressMs");
  });

  it("builds an offlineSummary from before/after catch-up", () => {
    const before = initialSnapshot();
    const after = advance(before, 2_160_000, { rateScale: OFFLINE_RATE_SCALE });
    const summary = buildOfflineSummary({
      before,
      after,
      offlineMs: 2_160_000,
    });
    expect(summary).toEqual({
      offlineMs: 2_160_000,
      advanceGained: 1,
      oreProduced:
        after.ore -
        before.ore +
        (after.bagOre - before.bagOre) +
        (after.ingots - before.ingots),
      oreSmelted: after.ingots - before.ingots,
      oreBacklog: after.ore,
    });
  });

  it("counts Ore drops that never break a Face toward oreProduced", () => {
    const before = initialSnapshot();
    const after = advance(before, 10_000);
    const summary = buildOfflineSummary({
      before,
      after,
      offlineMs: 10_000,
    });
    expect(summary.advanceGained).toBe(0);
    expect(summary.oreProduced).toBeCloseTo(1, 10);
  });

  it("counts Heap Ore toward oreProduced in offline summary", () => {
    const before = { ...initialSnapshot(), heapOre: 2 };
    const after = { ...before, heapOre: 9 };
    const summary = buildOfflineSummary({
      before,
      after,
      offlineMs: 60_000,
    });
    expect(summary.oreProduced).toBe(7);
  });

  describe("wire Snapshot change detection", () => {
    const base = toWireSnapshot(initialSnapshot());

    it("treats a missing prior Snapshot as changed", () => {
      expect(wireSnapshotChanged(null, base)).toBe(true);
    });

    it("ignores identical wire Snapshots", () => {
      expect(wireSnapshotChanged(base, { ...base })).toBe(false);
    });

    it("detects Face swing progress drift between wire Snapshots", () => {
      expect(
        wireSnapshotChanged(base, { ...base, faceSwingProgress: base.faceSwingProgress + 1 }),
      ).toBe(true);
    });

    it("detects offlineSummary arriving on the wire", () => {
      const summary = buildOfflineSummary({
        before: initialSnapshot(),
        after: advance(initialSnapshot(), 10_000),
        offlineMs: 10_000,
      });
      expect(
        wireSnapshotChanged(base, toWireSnapshot(initialSnapshot(), summary)),
      ).toBe(true);
    });

    it("detects offlineSummary clearing from the wire", () => {
      const summary = buildOfflineSummary({
        before: initialSnapshot(),
        after: advance(initialSnapshot(), 10_000),
        offlineMs: 10_000,
      });
      const withSummary = toWireSnapshot(initialSnapshot(), summary);
      expect(wireSnapshotChanged(withSummary, base)).toBe(true);
    });
  });
});

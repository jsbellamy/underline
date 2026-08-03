import { describe, expect, it } from "vitest";
import {
  OFFLINE_RATE_SCALE,
  advance,
  initialSnapshot,
} from "./mining-engine";
import { buildOfflineSummary, toWireSnapshot } from "./wire-snapshot";

describe("wire Snapshot", () => {
  it("projects save-authoritative fields for the Dock", () => {
    const snap = {
      ...initialSnapshot(),
      advance: 2,
      ore: 1.25,
      ingots: 3,
      digRateUpgradeCount: 1,
      faceSwingProgress: 2,
      smelterProgress: 0.3,
    };
    expect(toWireSnapshot(snap)).toEqual({
      schemaVersion: 2,
      advance: 2,
      ore: 1.25,
      ingots: 3,
      digRateUpgradeCount: 1,
      smelterUpgradeCount: 0,
      faceSwingProgress: 2,
      smelterProgress: 0.3,
    });
  });

  it("builds an offlineSummary from before/after catch-up", () => {
    const before = initialSnapshot();
    const after = advance(before, 2_000_000, { rateScale: OFFLINE_RATE_SCALE });
    const summary = buildOfflineSummary({
      before,
      after,
      offlineMs: 2_000_000,
    });
    expect(summary).toEqual({
      offlineMs: 2_000_000,
      advanceGained: 1,
      oreProduced: 1,
      oreSmelted: 1,
      oreBacklog: after.ore,
    });
  });
});

import { describe, expect, it } from "vitest";
import { initialSnapshot } from "./mining-engine";
import { tripPhaseFor } from "./trip-phase";

function snap(haulRemainingMs: number, unloadSpeedUpgradeCount = 0) {
  return {
    ...initialSnapshot(),
    haulRemainingMs,
    unloadSpeedUpgradeCount,
  };
}

describe("tripPhaseFor", () => {
  describe("zero Unload Speed upgrades (unloadMs 4000, round trip 8000)", () => {
    const cases: Array<[number, "out" | "unload" | "back" | null]> = [
      [8000, "out"],
      [6001, "out"],
      [6000, "unload"],
      [2001, "unload"],
      [2000, "back"],
      [1, "back"],
      [0, null],
    ];

    it.each(cases)("haulRemainingMs %i → %s", (haulRemainingMs, leg) => {
      const phase = tripPhaseFor(snap(haulRemainingMs));
      if (leg === null) {
        expect(phase).toBeNull();
      } else {
        expect(phase!.leg).toBe(leg);
      }
    });

    it("tripProgress at trip start is 0", () => {
      expect(tripPhaseFor(snap(8000))!.tripProgress).toBe(0);
    });

    it("tripProgress at midpoint is 0.5", () => {
      expect(tripPhaseFor(snap(4000))!.tripProgress).toBe(0.5);
    });
  });

  describe("one Unload Speed upgrade (unloadMs ≈ 2667, round trip ≈ 6667)", () => {
    const cases: Array<[number, "out" | "unload" | "back"]> = [
      [4667, "out"],
      [4666, "unload"],
      [2001, "unload"],
      [2000, "back"],
    ];

    it.each(cases)("haulRemainingMs %i → %s", (haulRemainingMs, leg) => {
      expect(tripPhaseFor(snap(haulRemainingMs, 1))!.leg).toBe(leg);
    });
  });
});

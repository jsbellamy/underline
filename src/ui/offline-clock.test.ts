import { describe, expect, it } from "vitest";
import {
  computeOfflineMs,
  MIN_OFFLINE_MS,
  OFFLINE_CAP_MS,
} from "./offline-clock";

describe("computeOfflineMs", () => {
  it("clamps offline duration to the 8h cap", () => {
    const savedAt = 0;
    const now = OFFLINE_CAP_MS + 60_000;
    expect(computeOfflineMs(savedAt, now)).toBe(OFFLINE_CAP_MS);
  });

  it("returns the raw elapsed when between min and cap", () => {
    const savedAt = 1_000;
    const elapsed = MIN_OFFLINE_MS + 5_000;
    expect(computeOfflineMs(savedAt, savedAt + elapsed)).toBe(elapsed);
  });

  it("returns 0 when savedAt is missing or non-finite", () => {
    expect(computeOfflineMs(undefined, 10_000)).toBe(0);
    expect(computeOfflineMs(Number.NaN, 10_000)).toBe(0);
  });

  it("floors negative elapsed at 0", () => {
    expect(computeOfflineMs(5_000, 1_000)).toBe(0);
  });
});

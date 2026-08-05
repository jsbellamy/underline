import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
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

describe("offline-clock module layout", () => {
  it("has no ui re-export shim", () => {
    expect(
      existsSync(join(dirname(fileURLToPath(import.meta.url)), "../ui/offline-clock.ts")),
    ).toBe(false);
  });

  it("cites Nightglass provenance per ADR 0009", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "offline-clock.ts"),
      "utf8",
    );
    expect(source).toMatch(/Source: nightglass\/src\/ui\/boot\.ts/);
    expect(source).toMatch(/7047b2a28565d28598a4420b8762c7f49b1898f5/);
    expect(source).toMatch(/Vendored: 2026-08-03/);
  });
});

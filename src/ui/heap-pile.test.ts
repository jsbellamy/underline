import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import tunnelManifest from "../assets/tunnel/manifest.json";
import {
  tunnelArtKeysUnder,
  tunnelArtPath,
  type TunnelArtPack,
} from "../data/tunnel-art-pack";
import { fallingOrePosition, haulerPickupTargetX, heapSlot } from "./heap-pile";
import {
  FACE_X,
  HAULER_MARK_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_ROW_HEIGHT,
  HEAP_SLOTS_PER_ROW,
  ORE_FALL_MS,
  ORE_PITCH,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";

describe("heapSlot", () => {
  it("exports layout constants with worked values", () => {
    expect(ORE_SIZE).toBe(32);
    expect(ORE_PITCH).toBe(36);
    expect(HEAP_ROW_HEIGHT).toBe(34);
    expect(HEAP_BOTTOM).toBe(8);
    expect(HEAP_EAST_X).toBe(400);
    expect(HEAP_SLOTS_PER_ROW).toBe(6);
    expect(HEAP_EAST_X).toBe(FACE_X - ORE_SIZE);
  });

  it("binds layout to gold ore object canvas size", () => {
    const pack = tunnelManifest as TunnelArtPack;
    const keys = tunnelArtKeysUnder(pack, "objects/ore/gold-");
    for (const key of keys) {
      const path = tunnelArtPath(pack, key);
      const buf = readFileSync(path);
      const width = buf.readUInt32BE(16);
      const height = buf.readUInt32BE(20);
      expect(width).toBe(ORE_SIZE);
      expect(height).toBe(ORE_SIZE);
    }
  });

  it("keeps the westmost slot east of the Hauler stand", () => {
    expect(heapSlot(HEAP_SLOTS_PER_ROW - 1).left).toBeGreaterThanOrEqual(
      HAULER_MARK_X,
    );
  });

  const worked: Array<{ index: number; left: number; bottom: number }> = [
    { index: 0, left: 400, bottom: 8 },
    { index: 1, left: 364, bottom: 8 },
    { index: 5, left: 220, bottom: 8 },
    { index: 6, left: 400, bottom: 42 },
    { index: 11, left: 220, bottom: 42 },
    { index: 12, left: 400, bottom: 76 },
  ];

  for (const { index, left, bottom } of worked) {
    it(`positions slot ${index} at left ${left} bottom ${bottom}`, () => {
      expect(heapSlot(index)).toEqual({ left, bottom });
    });
  }

  it("throws for a negative index", () => {
    expect(() => heapSlot(-1)).toThrow();
  });

  it("throws for a fractional index", () => {
    expect(() => heapSlot(1.5)).toThrow();
  });
});

describe("fallingOrePosition", () => {
  it("exports fall constants with worked values", () => {
    expect(ORE_FALL_MS).toBe(250);
    expect(ORE_SPAWN_BOTTOM).toBe(56);
  });

  const worked: Array<{
    slot: number;
    progress: number;
    left: number;
    bottom: number;
  }> = [
    { slot: 0, progress: 0, left: 400, bottom: 56 },
    { slot: 0, progress: 0.5, left: 400, bottom: 44 },
    { slot: 0, progress: 1, left: 400, bottom: 8 },
    { slot: 5, progress: 0, left: 400, bottom: 56 },
    { slot: 5, progress: 0.5, left: 310, bottom: 44 },
    { slot: 5, progress: 1, left: 220, bottom: 8 },
  ];

  for (const { slot, progress, left, bottom } of worked) {
    it(`slot ${slot} at progress ${progress} is left ${left} bottom ${bottom}`, () => {
      expect(fallingOrePosition(slot, progress)).toEqual({ left, bottom });
    });
  }

  it("at progress 1 deep-equals heapSlot for every worked slot", () => {
    for (const slot of [0, 5]) {
      expect(fallingOrePosition(slot, 1)).toEqual(heapSlot(slot));
    }
  });

  it("throws when progress is outside 0…1", () => {
    expect(() => fallingOrePosition(0, -0.1)).toThrow();
    expect(() => fallingOrePosition(0, 1.1)).toThrow();
  });
});

describe("haulerPickupTargetX", () => {
  const worked: Array<{ heapLoads: number; target: number }> = [
    { heapLoads: 1, target: 322 },
    { heapLoads: 3, target: 250 },
    { heapLoads: 5, target: 192 },
    { heapLoads: 6, target: 192 },
    { heapLoads: 10, target: 214 },
    { heapLoads: 20, target: 286 },
  ];

  for (const { heapLoads, target } of worked) {
    it(`targets x ${target} when heapLoads is ${heapLoads}`, () => {
      expect(haulerPickupTargetX(heapLoads)).toBe(target);
    });
  }

  it("throws when heapLoads is zero or negative", () => {
    expect(() => haulerPickupTargetX(0)).toThrow();
    expect(() => haulerPickupTargetX(-1)).toThrow();
  });

  it("never targets west of the Hauler stand", () => {
    for (const n of [1, 3, 5, 6, 10, 20]) {
      expect(haulerPickupTargetX(n)).toBeGreaterThanOrEqual(HAULER_MARK_X);
    }
  });
});

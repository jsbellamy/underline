import { describe, expect, it } from "vitest";
import { fallingOrePosition, haulerPickupTargetX, heapSlot } from "./heap-pile";
import {
  FACE_X,
  HAULER_MARK_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_ROW_HEIGHT,
  HEAP_SLOTS_PER_ROW,
  ORE_FALL_MS,
  ORE_LOGICAL_SIZE,
  ORE_PITCH,
  ORE_SCALE,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";

describe("heapSlot", () => {
  it("exports layout constants with worked values", () => {
    expect(ORE_LOGICAL_SIZE).toBe(8);
    expect(ORE_SCALE).toBe(2);
    expect(ORE_SIZE).toBe(16);
    expect(ORE_SIZE).toBe(ORE_LOGICAL_SIZE * ORE_SCALE);
    expect(ORE_PITCH).toBe(20);
    expect(HEAP_ROW_HEIGHT).toBe(18);
    expect(HEAP_BOTTOM).toBe(8);
    expect(HEAP_EAST_X).toBe(416);
    expect(HEAP_SLOTS_PER_ROW).toBe(12);
    expect(HEAP_EAST_X).toBe(FACE_X - ORE_SIZE);
  });

  it("keeps the westmost slot east of the Hauler stand", () => {
    expect(heapSlot(HEAP_SLOTS_PER_ROW - 1).left).toBeGreaterThanOrEqual(
      HAULER_MARK_X,
    );
  });

  const worked: Array<{ index: number; left: number; bottom: number }> = [
    { index: 0, left: 416, bottom: 8 },
    { index: 1, left: 396, bottom: 8 },
    { index: 11, left: 196, bottom: 8 },
    { index: 12, left: 416, bottom: 26 },
    { index: 23, left: 196, bottom: 26 },
    { index: 24, left: 416, bottom: 44 },
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
    { slot: 0, progress: 0, left: 416, bottom: 56 },
    { slot: 0, progress: 0.5, left: 416, bottom: 44 },
    { slot: 0, progress: 1, left: 416, bottom: 8 },
    { slot: 11, progress: 0, left: 416, bottom: 56 },
    { slot: 11, progress: 0.5, left: 306, bottom: 44 },
    { slot: 11, progress: 1, left: 196, bottom: 8 },
  ];

  for (const { slot, progress, left, bottom } of worked) {
    it(`slot ${slot} at progress ${progress} is left ${left} bottom ${bottom}`, () => {
      expect(fallingOrePosition(slot, progress)).toEqual({ left, bottom });
    });
  }

  it("at progress 1 deep-equals heapSlot for every worked slot", () => {
    for (const slot of [0, 11]) {
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
    { heapLoads: 1, target: 338 },
    { heapLoads: 5, target: 258 },
    { heapLoads: 10, target: 192 },
    { heapLoads: 12, target: 192 },
    { heapLoads: 20, target: 198 },
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
    for (const n of [1, 5, 10, 12, 20]) {
      expect(haulerPickupTargetX(n)).toBeGreaterThanOrEqual(HAULER_MARK_X);
    }
  });
});

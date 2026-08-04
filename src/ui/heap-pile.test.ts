import { describe, expect, it } from "vitest";
import { haulerPickupTargetX, heapSlot } from "./heap-pile";
import {
  FACE_X,
  HAULER_MARK_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_ROW_HEIGHT,
  HEAP_SLOTS_PER_ROW,
  ORE_PITCH,
  ORE_SIZE,
} from "./pane-layout";

describe("heapSlot", () => {
  it("exports layout constants with worked values", () => {
    expect(ORE_SIZE).toBe(8);
    expect(ORE_PITCH).toBe(12);
    expect(HEAP_ROW_HEIGHT).toBe(10);
    expect(HEAP_BOTTOM).toBe(8);
    expect(HEAP_EAST_X).toBe(328);
    expect(HEAP_SLOTS_PER_ROW).toBe(13);
    expect(HEAP_EAST_X).toBe(FACE_X - ORE_SIZE);
  });

  const worked: Array<{ index: number; left: number; bottom: number }> = [
    { index: 0, left: 328, bottom: 8 },
    { index: 1, left: 316, bottom: 8 },
    { index: 12, left: 184, bottom: 8 },
    { index: 13, left: 328, bottom: 18 },
    { index: 25, left: 184, bottom: 18 },
    { index: 26, left: 328, bottom: 28 },
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

describe("haulerPickupTargetX", () => {
  const worked: Array<{ heapLoads: number; target: number }> = [
    { heapLoads: 1, target: 250 },
    { heapLoads: 5, target: 202 },
    { heapLoads: 10, target: 142 },
    { heapLoads: 13, target: 106 },
    { heapLoads: 20, target: 178 },
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
    for (const n of [1, 5, 10, 13, 20]) {
      expect(haulerPickupTargetX(n)).toBeGreaterThanOrEqual(HAULER_MARK_X);
    }
  });
});

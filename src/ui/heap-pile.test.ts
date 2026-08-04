import { describe, expect, it } from "vitest";
import { heapSlot } from "./heap-pile";
import {
  FACE_X,
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

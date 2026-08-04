import { describe, expect, it } from "vitest";
import { fallingOrePosition, haulerPickupTargetX, heapSlot } from "./heap-pile";
import {
  FACE_X,
  HAULER_MARK_X,
  HAULER_PICKUP_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_ROW_HEIGHT,
  HEAP_SLOTS_PER_ROW,
  MINING_MARK_X,
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

  describe("heap destination", () => {
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
        expect(fallingOrePosition("heap", slot, progress)).toEqual({ left, bottom });
      });
    }

    it("at progress 1 deep-equals heapSlot for every worked slot", () => {
      for (const slot of [0, 5]) {
        expect(fallingOrePosition("heap", slot, 1)).toEqual(heapSlot(slot));
      }
    });
  });

  describe("bag destination", () => {
    const bagLeft = MINING_MARK_X + Math.round((26 * 3 - ORE_SIZE) / 2);

    const worked: Array<{
      progress: number;
      left: number;
      bottom: number;
    }> = [
      { progress: 0, left: HEAP_EAST_X, bottom: ORE_SPAWN_BOTTOM },
      { progress: 0.5, left: 389, bottom: 44 },
      { progress: 1, left: bagLeft, bottom: HEAP_BOTTOM },
    ];

    for (const { progress, left, bottom } of worked) {
      it(`at progress ${progress} is left ${left} bottom ${bottom}`, () => {
        expect(fallingOrePosition("bag", 0, progress)).toEqual({ left, bottom });
      });
    }
  });

  it("throws when progress is outside 0…1", () => {
    expect(() => fallingOrePosition("heap", 0, -0.1)).toThrow();
    expect(() => fallingOrePosition("heap", 0, 1.1)).toThrow();
    expect(() => fallingOrePosition("bag", 0, -0.1)).toThrow();
    expect(() => fallingOrePosition("bag", 0, 1.1)).toThrow();
  });
});

describe("haulerPickupTargetX", () => {
  it("defines a fixed pickup mark 130 px east of the Hauler stand", () => {
    expect(HAULER_PICKUP_X).toBe(322);
  });

  const representativeDepths = [1, 3, 5, 6, 10, 20];

  for (const heapLoads of representativeDepths) {
    it(`returns the fixed pickup mark when heapLoads is ${heapLoads}`, () => {
      expect(haulerPickupTargetX(heapLoads)).toBe(322);
    });
  }

  it("throws when heapLoads is zero or negative", () => {
    expect(() => haulerPickupTargetX(0)).toThrow();
    expect(() => haulerPickupTargetX(-1)).toThrow();
  });
});

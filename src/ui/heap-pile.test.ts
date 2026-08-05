import { describe, expect, it } from "vitest";
import { fallingOrePosition, haulerPickupTargetX } from "./heap-pile";
import {
  DWARF_FRAME_W,
  DWARF_SCALE,
  FACE_X,
  HAULER_GRAB_X,
  HAULER_MARK_X,
  HAULER_PICKUP_X,
  HEAP_BIN_CEILING_Y,
  HEAP_BIN_EAST_X,
  HEAP_BIN_FLOOR_Y,
  HEAP_BIN_WEST_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_GRAB_Y,
  HEAP_PILE_SEED,
  HEAP_RENDER_CEILING,
  HEAP_SPAWN_X,
  MINING_MARK_X,
  ORE_FALL_MS,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
  PANE_HEIGHT,
} from "./pane-layout";

describe("pane-layout heap exports", () => {
  it("exports surviving layout constants with worked values", () => {
    expect(ORE_SIZE).toBe(32);
    expect(HEAP_BOTTOM).toBe(8);
    expect(HEAP_EAST_X).toBe(400);
    expect(ORE_SPAWN_BOTTOM).toBe(56);
    expect(HEAP_EAST_X).toBe(FACE_X - ORE_SIZE);
  });

  it("exports heap bin and pile constants with worked values", () => {
    expect(HEAP_RENDER_CEILING).toBe(20);
    expect(HEAP_BIN_FLOOR_Y).toBe(8);
    expect(HEAP_BIN_WEST_X).toBe(192);
    expect(HEAP_BIN_EAST_X).toBe(432);
    expect(HEAP_BIN_CEILING_Y).toBe(112);
    expect(HEAP_SPAWN_X).toBe(416);
    expect(HAULER_GRAB_X).toBe(361);
    expect(HEAP_GRAB_Y).toBe(24);
    expect(HEAP_GRAB_Y).toBe(HEAP_BIN_FLOOR_Y + ORE_SIZE / 2);
    expect(HEAP_PILE_SEED).toBe(1);
    expect(HEAP_BIN_FLOOR_Y).toBe(HEAP_BOTTOM);
    expect(HEAP_BIN_WEST_X).toBe(HAULER_MARK_X);
    expect(HEAP_BIN_EAST_X).toBe(FACE_X);
    expect(HEAP_BIN_CEILING_Y).toBe(PANE_HEIGHT);
    expect(HEAP_SPAWN_X).toBe(FACE_X - ORE_SIZE / 2);
    expect(HAULER_GRAB_X).toBe(
      HAULER_PICKUP_X + (DWARF_FRAME_W * DWARF_SCALE) / 2,
    );
  });
});

describe("fallingOrePosition", () => {
  it("exports fall constants with worked values", () => {
    expect(ORE_FALL_MS).toBe(250);
    expect(ORE_SPAWN_BOTTOM).toBe(56);
  });

  describe("bag arc", () => {
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
        expect(fallingOrePosition(0, progress)).toEqual({ left, bottom });
      });
    }
  });

  it("throws when progress is outside 0…1", () => {
    expect(() => fallingOrePosition(0, -0.1)).toThrow();
    expect(() => fallingOrePosition(0, 1.1)).toThrow();
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

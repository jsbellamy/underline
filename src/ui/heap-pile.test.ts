import { describe, expect, it } from "vitest";
import { fallingOrePosition } from "./heap-pile";
import {
  CART_MARK_X,
  CART_WIDTH,
  FACE_X,
  HAULER_MARK_X,
  HAULER_WALK_PX_PER_MS,
  haulerStationFor,
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
import { HAUL_TRAVEL_MS } from "../core/mining-engine";

describe("pane-layout hauler walk", () => {
  it("walks the widest tunnel lane in one travel leg", () => {
    expect(HAULER_WALK_PX_PER_MS).toBe(
      (HEAP_BIN_EAST_X - CART_MARK_X) / (HAUL_TRAVEL_MS / 2),
    );
  });

  it("maps a body x to the Hauler sprite left with tunnel clamps", () => {
    expect(haulerStationFor(401)).toBe(345);
    expect(haulerStationFor(1000)).toBe(354);
    expect(haulerStationFor(0)).toBe(152);
  });
});

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
    expect(HEAP_GRAB_Y).toBe(24);
    expect(HEAP_GRAB_Y).toBe(HEAP_BIN_FLOOR_Y + ORE_SIZE / 2);
    expect(HEAP_PILE_SEED).toBe(1);
    expect(HEAP_BIN_FLOOR_Y).toBe(HEAP_BOTTOM);
    expect(HAULER_MARK_X).toBe(CART_MARK_X);
    expect(HEAP_BIN_WEST_X).toBe(CART_MARK_X + CART_WIDTH);
    expect(HEAP_BIN_EAST_X).toBe(FACE_X);
    expect(HEAP_BIN_CEILING_Y).toBe(PANE_HEIGHT);
    expect(HEAP_SPAWN_X).toBe(FACE_X - ORE_SIZE / 2);
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

import { describe, expect, it } from "vitest";
import {
  HEAP_ORE_KEYS,
  HEAP_ORE_VARIANT_COUNT,
  heapOreArtKey,
  heapOreContentCenter,
  heapOreRadius,
} from "./heap-ore-variants";

describe("heap-ore-variants", () => {
  it("exports six sorted gold ore keys", () => {
    expect(HEAP_ORE_KEYS).toHaveLength(6);
    expect([...HEAP_ORE_KEYS]).toEqual([
      "objects/ore/gold-large-a",
      "objects/ore/gold-large-b",
      "objects/ore/gold-large-c",
      "objects/ore/gold-medium-a",
      "objects/ore/gold-medium-b",
      "objects/ore/gold-small",
    ]);
    expect(HEAP_ORE_VARIANT_COUNT).toBe(6);
  });

  it("resolves variant 0 to gold-large-a", () => {
    expect(heapOreArtKey(0)).toBe("objects/ore/gold-large-a");
  });

  const radiusWorked: Array<{ index: number; radius: number }> = [
    { index: 0, radius: 12 },
    { index: 1, radius: 13.75 },
    { index: 2, radius: 14 },
    { index: 3, radius: 9.5 },
    { index: 4, radius: 10 },
    { index: 5, radius: 6 },
  ];

  for (const { index, radius } of radiusWorked) {
    it(`returns radius ${radius} for variant ${index}`, () => {
      expect(heapOreRadius(index)).toBe(radius);
    });
  }

  const centerWorked: Array<{ index: number; cx: number }> = [
    { index: 0, cx: 16 },
    { index: 1, cx: 15.5 },
    { index: 2, cx: 16 },
    { index: 3, cx: 16 },
    { index: 4, cx: 16 },
    { index: 5, cx: 16 },
  ];

  for (const { index, cx } of centerWorked) {
    it(`returns content centre cx ${cx} cyFromBottom 16 for variant ${index}`, () => {
      expect(heapOreContentCenter(index)).toEqual({ cx, cyFromBottom: 16 });
    });
  }

  it("throws for out-of-range or non-integer variant indices", () => {
    for (const fn of [heapOreArtKey, heapOreRadius, heapOreContentCenter]) {
      expect(() => fn(-1)).toThrow();
      expect(() => fn(6)).toThrow();
      expect(() => fn(1.5)).toThrow();
    }
  });
});

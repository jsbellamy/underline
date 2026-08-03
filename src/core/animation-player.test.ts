import { describe, expect, it } from "vitest";
import { frameAt, type AnimationPlayback } from "./animation-player";

describe("frameAt", () => {
  const threeFrame: AnimationPlayback = {
    durationsMs: [100, 200, 100],
    loop: true,
  };

  it("returns the first frame at elapsed 0", () => {
    expect(frameAt(threeFrame, 0)).toBe(0);
  });

  it("advances through frames by cumulative duration", () => {
    expect(frameAt(threeFrame, 99)).toBe(0);
    expect(frameAt(threeFrame, 100)).toBe(1);
    expect(frameAt(threeFrame, 299)).toBe(1);
    expect(frameAt(threeFrame, 300)).toBe(2);
  });

  it("loops when elapsed exceeds the cycle", () => {
    // cycle = 400ms
    expect(frameAt(threeFrame, 400)).toBe(0);
    expect(frameAt(threeFrame, 500)).toBe(1);
  });

  it("holds the last frame when not looping past the end", () => {
    const oneShot: AnimationPlayback = {
      durationsMs: [50, 50, 50],
      loop: false,
    };
    expect(frameAt(oneShot, 149)).toBe(2);
    expect(frameAt(oneShot, 150)).toBe(2);
    expect(frameAt(oneShot, 10_000)).toBe(2);
  });

  it("rejects empty duration lists", () => {
    expect(() => frameAt({ durationsMs: [], loop: true }, 0)).toThrow(
      /durationsMs/,
    );
  });
});

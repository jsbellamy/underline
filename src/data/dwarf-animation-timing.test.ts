import { describe, expect, it } from "vitest";
import {
  dwarfPlayback,
  SWING_FRAME_COUNT,
  SWING_IMPACT_FRAME,
  WALK_FRAME_COUNT,
} from "./dwarf-animation-timing";
import { cycleDurationMs } from "../core/animation-player";

describe("dwarfAnimationTiming", () => {
  it("declares idle as a looping single frame", () => {
    const idle = dwarfPlayback("idle", 1);
    expect(idle.loop).toBe(true);
    expect(idle.durationsMs).toHaveLength(1);
  });

  it("declares the pick-contact frame as a valid swing index", () => {
    expect(SWING_IMPACT_FRAME).toBe(5);
    expect(SWING_IMPACT_FRAME).toBeLessThan(SWING_FRAME_COUNT);
  });

  it("declares swing as a looping clip whose cycle is 1/Dig Rate seconds", () => {
    const atOne = dwarfPlayback("swing", 1);
    expect(atOne.loop).toBe(true);
    expect(atOne.durationsMs).toHaveLength(SWING_FRAME_COUNT);
    expect(cycleDurationMs(atOne)).toBe(1000);

    const atTwo = dwarfPlayback("swing", 2);
    expect(cycleDurationMs(atTwo)).toBe(500);
  });

  it("declares walk as a looping clip independent of Dig Rate", () => {
    const walk = dwarfPlayback("walk", 1);
    expect(walk.loop).toBe(true);
    expect(walk.durationsMs).toHaveLength(WALK_FRAME_COUNT);
    expect(cycleDurationMs(walk)).toBe(400);

    const atTwo = dwarfPlayback("walk", 2);
    expect(atTwo.loop).toBe(true);
    expect(cycleDurationMs(atTwo)).toBe(400);
  });
});

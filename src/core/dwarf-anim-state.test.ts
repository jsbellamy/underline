import { describe, expect, it } from "vitest";
import {
  createDwarfAnimController,
  type DwarfAnimId,
} from "./dwarf-anim-state";
import { dwarfPlayback, SWING_FRAME_COUNT } from "../data/dwarf-animation-timing";

describe("dwarf anim state", () => {
  it("starts idle facing east", () => {
    const ctrl = createDwarfAnimController();
    expect(ctrl.animation).toBe("idle");
    expect(ctrl.facing).toBe("east");
  });

  it("enters swing when mining starts", () => {
    const ctrl = createDwarfAnimController();
    ctrl.startMining(0);
    expect(ctrl.animation).toBe("swing");
    expect(ctrl.facing).toBe("east");
  });

  it("enters walk facing west when hauling out", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining(0);
    ctrl.setHauling("out", 100);
    expect(ctrl.animation).toBe("walk");
    expect(ctrl.facing).toBe("west");
  });

  it("enters walk facing east when hauling back", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining(0);
    ctrl.setHauling("back", 100);
    expect(ctrl.animation).toBe("walk");
    expect(ctrl.facing).toBe("east");
  });

  it("returns to swing when hauling ends while mining", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining(0);
    ctrl.setHauling("out", 100);
    ctrl.setHauling(null, 500);
    expect(ctrl.animation).toBe("swing");
    expect(ctrl.facing).toBe("east");
  });

  it("returns to idle when hauling ends while not mining", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.setHauling("out", 0);
    ctrl.setHauling(null, 500);
    expect(ctrl.animation).toBe("idle");
    expect(ctrl.facing).toBe("east");
  });

  it("does not restart the walk clip when setHauling repeats the same phase", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining(0);
    ctrl.setHauling("out", 100);
    const frameBefore = ctrl.frameIndexAt(300);
    ctrl.setHauling("out", 300);
    expect(ctrl.frameIndexAt(300)).toBe(frameBefore);
  });

  it("loops walk for the whole haul leg", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining(0);
    ctrl.setHauling("out", 0);
    const walk = dwarfPlayback("walk", 1);
    const cycleMs = walk.durationsMs.reduce((a, b) => a + b, 0);
    expect(ctrl.frameIndexAt(cycleMs * 3)).toBe(0);
    expect(ctrl.frameIndexAt(cycleMs * 3 + 200)).toBe(4);
    expect(ctrl.animation).toBe("walk");
  });

  it("walk loops on a 400 ms cycle independent of Dig Rate", () => {
    const ctrl = createDwarfAnimController({ digRate: 2 });
    ctrl.startMining(0);
    ctrl.setHauling("out", 0);
    expect(ctrl.frameIndexAt(0)).toBe(0);
    expect(ctrl.frameIndexAt(400)).toBe(0);
    expect(ctrl.frameIndexAt(200)).toBeGreaterThan(0);
  });

  it("does not leave swing for idle while still mining", () => {
    const ctrl = createDwarfAnimController();
    ctrl.startMining(0);
    expect(ctrl.animation).toBe("swing");
  });

  it("reports frame 0 at clip start and advances with absolute nowMs", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining(1000);
    expect(ctrl.frameIndexAt(1000)).toBe(0);
    // Dig Rate 1.0 → 1000ms swing cycle over 9 frames ≈ 111.11ms each
    expect(ctrl.frameIndexAt(1112)).toBe(1);
  });

  it("maps swing fraction to frame index with impact at fraction 0", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    expect(ctrl.frameIndexForSwingFraction(0)).toBe(5);
    expect(ctrl.frameIndexForSwingFraction(4 / SWING_FRAME_COUNT)).toBe(0);

    const expectedOrder = [5, 6, 7, 8, 0, 1, 2, 3, 4];
    for (let i = 0; i < SWING_FRAME_COUNT; i += 1) {
      const fraction = (i + 0.5) / SWING_FRAME_COUNT;
      expect(ctrl.frameIndexForSwingFraction(fraction)).toBe(expectedOrder[i]);
    }
    expect(ctrl.frameIndexForSwingFraction(1)).toBe(5);
  });

  it("only selects among idle, swing, and walk", () => {
    const allowed: readonly DwarfAnimId[] = ["idle", "swing", "walk"];
    const ctrl = createDwarfAnimController();
    expect(allowed).toContain(ctrl.animation);
    ctrl.startMining(0);
    expect(allowed).toContain(ctrl.animation);
    ctrl.setHauling("out", 100);
    expect(allowed).toContain(ctrl.animation);
  });
});

import { describe, expect, it } from "vitest";
import {
  createDwarfAnimController,
  type DwarfAnimId,
} from "./dwarf-anim-state";
import { dwarfPlayback } from "../data/dwarf-animation-timing";

describe("dwarf anim state", () => {
  it("starts idle facing east", () => {
    const ctrl = createDwarfAnimController();
    expect(ctrl.animation).toBe("idle");
    expect(ctrl.facing).toBe("east");
  });

  it("enters swing when mining starts", () => {
    const ctrl = createDwarfAnimController();
    ctrl.startMining();
    expect(ctrl.animation).toBe("swing");
    expect(ctrl.facing).toBe("east");
  });

  it("enters walk facing west when hauling out", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.setHauling("out");
    expect(ctrl.animation).toBe("walk");
    expect(ctrl.facing).toBe("west");
  });

  it("enters walk facing east when hauling back", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.setHauling("back");
    expect(ctrl.animation).toBe("walk");
    expect(ctrl.facing).toBe("east");
  });

  it("returns to swing when hauling ends while mining", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.setHauling("out");
    ctrl.setHauling(null);
    expect(ctrl.animation).toBe("swing");
    expect(ctrl.facing).toBe("east");
  });

  it("returns to idle when hauling ends while not mining", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.setHauling("out");
    ctrl.setHauling(null);
    expect(ctrl.animation).toBe("idle");
    expect(ctrl.facing).toBe("east");
  });

  it("does not restart the walk clip when setHauling repeats the same phase", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.setHauling("out");
    ctrl.advanceMs(200);
    const elapsed = ctrl.clipElapsedMs;
    ctrl.setHauling("out");
    expect(ctrl.clipElapsedMs).toBe(elapsed);
  });

  it("loops walk for the whole haul leg", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.setHauling("out");
    const walk = dwarfPlayback("walk", 1);
    const cycleMs = walk.durationsMs.reduce((a, b) => a + b, 0);
    ctrl.advanceMs(cycleMs * 3);
    expect(ctrl.animation).toBe("walk");
  });

  it("does not leave swing for idle while still mining", () => {
    const ctrl = createDwarfAnimController();
    ctrl.startMining();
    ctrl.advanceMs(10_000);
    expect(ctrl.animation).toBe("swing");
  });

  it("exposes the current frame index from the animation player", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    expect(ctrl.frameIndex).toBe(0);
    // Dig Rate 1.0 → 1000ms swing cycle over 9 frames ≈ 111.11ms each
    ctrl.advanceMs(112);
    expect(ctrl.frameIndex).toBe(1);
  });

  it("only selects among idle, swing, and walk", () => {
    const allowed: readonly DwarfAnimId[] = ["idle", "swing", "walk"];
    const ctrl = createDwarfAnimController();
    expect(allowed).toContain(ctrl.animation);
    ctrl.startMining();
    expect(allowed).toContain(ctrl.animation);
    ctrl.setHauling("out");
    expect(allowed).toContain(ctrl.animation);
  });
});

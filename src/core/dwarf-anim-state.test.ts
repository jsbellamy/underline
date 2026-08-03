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
  });

  it("plays walk once when a Mineable Block breaks, then returns to swing", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.faceBroken();
    expect(ctrl.animation).toBe("walk");

    const walk = dwarfPlayback("walk", 1);
    ctrl.advanceMs(walk.durationsMs.reduce((a, b) => a + b, 0));
    expect(ctrl.animation).toBe("swing");
  });

  it("does not leave swing for idle while still mining", () => {
    const ctrl = createDwarfAnimController();
    ctrl.startMining();
    ctrl.advanceMs(10_000);
    expect(ctrl.animation).toBe("swing");
  });

  it("returns to idle when mining stops after the current walk finishes", () => {
    const ctrl = createDwarfAnimController({ digRate: 1 });
    ctrl.startMining();
    ctrl.faceBroken();
    ctrl.stopMining();
    expect(ctrl.animation).toBe("walk");
    const walk = dwarfPlayback("walk", 1);
    ctrl.advanceMs(walk.durationsMs.reduce((a, b) => a + b, 0));
    expect(ctrl.animation).toBe("idle");
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
    ctrl.faceBroken();
    expect(allowed).toContain(ctrl.animation);
  });
});

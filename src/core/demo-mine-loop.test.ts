import { describe, expect, it } from "vitest";
import {
  createDemoMineLoop,
  HARDNESS,
} from "./demo-mine-loop";

describe("demoMineLoop", () => {
  it("opens idle, then swings once mining starts", () => {
    const loop = createDemoMineLoop();
    expect(loop.snapshot().animation).toBe("idle");
    expect(loop.snapshot().advance).toBe(0);
    loop.start();
    expect(loop.snapshot().animation).toBe("swing");
  });

  it("breaks the Face after Hardness Swings and plays walk before the next Face", () => {
    const loop = createDemoMineLoop({ digRate: 1 });
    loop.start();
    // Hardness Swings at 1 Swing/sec → 4s to break; walk starts immediately after.
    loop.advanceMs(HARDNESS * 1000);
    expect(loop.snapshot().animation).toBe("walk");
    expect(loop.snapshot().advance).toBe(1);
    expect(loop.snapshot().faceSwingProgress).toBe(0);

    loop.advanceMs(400); // walk cycle
    expect(loop.snapshot().animation).toBe("swing");
  });

  it("keeps Advance growing across multiple breaks", () => {
    const loop = createDemoMineLoop({ digRate: 1 });
    loop.start();
    // Two faces: 4s swing + 0.4s walk + 4s swing
    loop.advanceMs(HARDNESS * 1000);
    loop.advanceMs(400);
    loop.advanceMs(HARDNESS * 1000);
    expect(loop.snapshot().advance).toBe(2);
    expect(loop.snapshot().animation).toBe("walk");
  });
});

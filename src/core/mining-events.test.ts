import { describe, expect, it } from "vitest";
import type { MiningEvent, MiningEventType } from "./mining-events";

describe("mining events vocabulary", () => {
  it("a mining event carries an unscaled atMs offset from the advance window", () => {
    const swingTypes: MiningEventType[] = ["swing", "faceBroken"];
    expect(swingTypes).toHaveLength(2);

    const swing: MiningEvent = { type: "swing", atMs: 1000 };
    const faceBroken: MiningEvent = { type: "faceBroken", atMs: 2500 };
    expect(swing.type).toBe("swing");
    expect(faceBroken.type).toBe("faceBroken");
    expect(swing.atMs).toBe(1000);
    expect(faceBroken.atMs).toBe(2500);
  });
});

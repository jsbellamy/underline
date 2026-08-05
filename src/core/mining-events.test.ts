import { describe, expect, it } from "vitest";
import type { MiningEvent, MiningEventType } from "./mining-events";

describe("mining events vocabulary", () => {
  it("a mining event carries an unscaled atMs offset from the advance window", () => {
    const eventTypes: MiningEventType[] = [
      "swing",
      "faceBroken",
      "loadDropped",
      "loadSpilled",
    ];
    expect(eventTypes).toHaveLength(4);

    const swing: MiningEvent = { type: "swing", atMs: 1000 };
    const faceBroken: MiningEvent = { type: "faceBroken", atMs: 2500 };
    const loadDropped: MiningEvent = { type: "loadDropped", atMs: 10_000 };
    const loadSpilled: MiningEvent = { type: "loadSpilled", atMs: 12_000 };
    expect(swing.type).toBe("swing");
    expect(faceBroken.type).toBe("faceBroken");
    expect(loadDropped.type).toBe("loadDropped");
    expect(loadSpilled.type).toBe("loadSpilled");
    expect(swing.atMs).toBe(1000);
    expect(faceBroken.atMs).toBe(2500);
    expect(loadDropped.atMs).toBe(10_000);
    expect(loadSpilled.atMs).toBe(12_000);
  });
});

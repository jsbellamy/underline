import { describe, expect, it } from "vitest";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot } from "../core/mining-engine";
import { createMinePresenter } from "./mine-presenter";

function memoryStore() {
  const data: Record<string, string> = {};
  return {
    getItem(key: string) {
      return data[key] ?? null;
    },
    setItem(key: string, value: string) {
      data[key] = value;
    },
    removeItem(key: string) {
      delete data[key];
    },
  };
}

describe("mine presenter", () => {
  it("syncDigRate mirrors digRateUpgradeCount into the anim Dig Rate", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), ingots: 5 },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    expect(presenter.anim.digRate).toBe(1);
    expect(session.tryBuyUpgrade()).toBe(true);
    presenter.syncDigRate();
    expect(presenter.anim.digRate).toBe(1.25);
    expect(presenter.snapshot().digRate).toBe(1.25);
  });

  it("grows Advance on the Tunnel snapshot as Faces break", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    // Live pump steps are 250ms; stop on the tick that breaks the Face so walk is visible.
    for (let i = 0; i < 16; i += 1) {
      presenter.advanceMs(250);
    }
    expect(presenter.snapshot().advance).toBe(1);
    expect(presenter.snapshot().animation).toBe("walk");
  });
});

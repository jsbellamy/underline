// @vitest-environment happy-dom

import { describe, expect, it } from "vitest";
import { mountMiningTunnel } from "./mining-tunnel";
import { BLOCK_SIZE, PANE_WIDTH } from "./pane-layout";

const VISIBLE_COLUMNS = Math.ceil(PANE_WIDTH / BLOCK_SIZE) + 2;

const baseSnap = {
  animation: "idle" as const,
  facing: "east" as const,
  frameIndex: 0,
  faceSwingProgress: 0,
  swingFraction: 0,
  digRate: 1,
};

function countDescendants(element: HTMLElement): number {
  return element.querySelectorAll("*").length;
}

function faceScreenLeft(host: HTMLElement, advance: number): number {
  const world = host.querySelector(".pane-tunnel-world") as HTMLElement;
  const transform = world.style.transform;
  const scrollX =
    transform === ""
      ? 0
      : -Number(transform.match(/translateX\((-?\d+(?:\.\d+)?)px\)/)?.[1] ?? 0);
  const blocks = world.querySelectorAll<HTMLElement>(".pane-block");
  for (const block of blocks) {
    const left = Number(block.style.left.replace("px", ""));
    const worldIndex = left / BLOCK_SIZE;
    if (worldIndex === advance) {
      return left - scrollX;
    }
  }
  throw new Error(`Face column not found at advance ${advance}`);
}

describe("mountMiningTunnel column pool", () => {
  it("keeps DOM node count constant as Advance grows", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render({ ...baseSnap, advance: 0 });
    const countAt0 = countDescendants(host);

    tunnel.render({ ...baseSnap, advance: 10000 });
    const countAt10000 = countDescendants(host);

    expect(countAt10000).toBe(countAt0);
    tunnel.destroy();
  });

  it("allocates a fixed column pool at mount before any render", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const world = host.querySelector(".pane-tunnel-world");
    expect(world).not.toBeNull();
    const columnsBeforeRender = world!.querySelectorAll(".pane-block");
    expect(columnsBeforeRender.length).toBe(VISIBLE_COLUMNS);

    tunnel.render({
      animation: "idle",
      facing: "east",
      frameIndex: 0,
      advance: 5000,
      faceSwingProgress: 0,
      swingFraction: 0,
      digRate: 1,
    });
    const columnsAfterRender = world!.querySelectorAll(".pane-block");
    expect(columnsAfterRender.length).toBe(VISIBLE_COLUMNS);

    tunnel.destroy();
  });

  it("does not mutate the DOM when rendering the same snapshot twice", async () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const snap = { ...baseSnap, advance: 50 };

    tunnel.render(snap);

    const observer = new MutationObserver(() => {});
    observer.observe(host, {
      childList: true,
      subtree: true,
      attributes: true,
      characterData: true,
    });

    tunnel.render(snap);
    await new Promise((r) => setTimeout(r, 0));

    expect(observer.takeRecords()).toEqual([]);
    observer.disconnect();
    tunnel.destroy();
  });

  it("places the Face at the same on-screen x as the scroll formula", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    for (const advance of [0, 13, 100, 5000, 10000]) {
      tunnel.render({ ...baseSnap, advance });
      const expected =
        advance * BLOCK_SIZE -
        Math.max(
          0,
          advance * BLOCK_SIZE - (PANE_WIDTH - BLOCK_SIZE - 16 - BLOCK_SIZE),
        );
      expect(faceScreenLeft(host, advance)).toBeCloseTo(expected, 5);
    }

    tunnel.destroy();
  });

  it("carries at most one Face crack element after any render", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    for (const advance of [0, 24, 25, 100, 5000]) {
      tunnel.render({
        animation: "swing",
        facing: "east",
        frameIndex: 0,
        advance,
        faceSwingProgress: 2,
        swingFraction: 0.5,
        digRate: 1,
      });
      expect(host.querySelectorAll(".pane-face-crack").length).toBeLessThanOrEqual(
        1,
      );
    }

    tunnel.destroy();
  });
});

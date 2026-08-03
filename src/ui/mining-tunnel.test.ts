// @vitest-environment happy-dom

import { describe, expect, it } from "vitest";
import {
  MINING_TUNNEL_VISIBLE_COLUMNS,
  mountMiningTunnel,
} from "./mining-tunnel";
import { BLOCK_SIZE } from "./pane-layout";

const baseSnap = {
  animation: "idle" as const,
  facing: "east" as const,
  frameIndex: 0,
  faceSwingProgress: 0,
  swingFraction: 0,
  digRate: 1,
  haulPhase: "none" as const,
  haulProgress: 0,
};

function countDescendants(element: HTMLElement): number {
  return element.querySelectorAll("*").length;
}

function blockAtWorldIndex(
  host: HTMLElement,
  worldIndex: number,
): HTMLElement {
  const blocks = host.querySelectorAll<HTMLElement>(".pane-block");
  for (const block of blocks) {
    const left = Number(block.style.left.replace("px", ""));
    if (left / BLOCK_SIZE === worldIndex) {
      return block;
    }
  }
  throw new Error(`No column at world index ${worldIndex}`);
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

describe("mountMiningTunnel", () => {
  it("keeps Tunnel DOM size constant as Advance grows", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render({ ...baseSnap, advance: 0 });
    const countAt0 = countDescendants(host);

    tunnel.render({ ...baseSnap, advance: 10000 });
    const countAt10000 = countDescendants(host);

    expect(countAt10000).toBe(countAt0);
    tunnel.destroy();
  });

  it("creates a fixed set of Mineable Block columns at mount", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const world = host.querySelector(".pane-tunnel-world");
    expect(world).not.toBeNull();
    const columnsBeforeRender = world!.querySelectorAll(".pane-block");
    expect(columnsBeforeRender.length).toBe(MINING_TUNNEL_VISIBLE_COLUMNS);

    tunnel.render({ ...baseSnap, advance: 5000 });
    const columnsAfterRender = world!.querySelectorAll(".pane-block");
    expect(columnsAfterRender.length).toBe(MINING_TUNNEL_VISIBLE_COLUMNS);

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

  it("keeps the Face at pinned screen x as Advance grows", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const pinnedScreenX: Array<{ advance: number; screenX: number }> = [
      { advance: 0, screenX: 0 },
      { advance: 13, screenX: 400 },
      { advance: 100, screenX: 400 },
      { advance: 5000, screenX: 400 },
      { advance: 10000, screenX: 400 },
    ];

    for (const { advance, screenX } of pinnedScreenX) {
      tunnel.render({ ...baseSnap, advance });
      expect(faceScreenLeft(host, advance)).toBe(screenX);
    }

    tunnel.destroy();
  });

  it("carries at most one Face crack after any render", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    for (const advance of [0, 24, 25, 100, 5000]) {
      tunnel.render({
        ...baseSnap,
        animation: "swing",
        advance,
        faceSwingProgress: 2,
        swingFraction: 0.5,
      });
      expect(host.querySelectorAll(".pane-face-crack").length).toBeLessThanOrEqual(
        1,
      );
    }

    tunnel.destroy();
  });

  it("paints hollow, solid, and Face Mineable Blocks with the Tunnel palette", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 10 });

    expect(blockAtWorldIndex(host, 5).style.background).toBe("#1D1720");
    expect(blockAtWorldIndex(host, 10).style.background).toBe("#27A6A3");
    expect(blockAtWorldIndex(host, 11).style.background).toBe("#4A3B48");

    tunnel.destroy();
  });

  it("deepens the Face and draws a crack when Swing progress is positive", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({
      ...baseSnap,
      animation: "swing",
      advance: 10,
      faceSwingProgress: 2,
    });

    const face = blockAtWorldIndex(host, 10);
    expect(face.style.background).toBe("#176873");
    expect(face.querySelector(".pane-face-crack")).not.toBeNull();

    tunnel.destroy();
  });

  it("positions the floor band across the visible Tunnel width", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 10 });

    const floor = host.querySelector<HTMLElement>(".pane-tunnel-floor");
    expect(floor).not.toBeNull();
    expect(floor!.style.left).toBe(`${-BLOCK_SIZE}px`);
    expect(floor!.style.width).toBe(
      `${MINING_TUNNEL_VISIBLE_COLUMNS * BLOCK_SIZE}px`,
    );

    tunnel.destroy();
  });

  it("sets Dwarf sprite src and frame attributes from the snapshot", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render({
      ...baseSnap,
      animation: "swing",
      facing: "west",
      frameIndex: 2,
      advance: 3,
    });

    const dwarf = host.querySelector<HTMLImageElement>("[data-dwarf]");
    expect(dwarf).not.toBeNull();
    expect(dwarf!.src).toMatch(/swing\/west\/frame_002\.png$/);
    expect(dwarf!.dataset["anim"]).toBe("swing");
    expect(dwarf!.dataset["frame"]).toBe("2");

    tunnel.destroy();
  });
});

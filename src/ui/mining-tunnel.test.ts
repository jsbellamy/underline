// @vitest-environment happy-dom

import { describe, expect, it } from "vitest";
import {
  MINING_TUNNEL_VISIBLE_COLUMNS,
  mountMiningTunnel,
} from "./mining-tunnel";
import type { TunnelSnapshot } from "./mine-presenter";
import { dwarfLayout } from "../data/external-sprite-pack";
import { DWARF_PACK } from "./dwarf-frames";
import { HAULER_PACK } from "./hauler-frames";
import {
  BLOCK_SIZE,
  CART_HEIGHT,
  CART_MARK_X,
  CART_WIDTH,
  CART_X,
  FACE_X,
  HAULER_MARK_X,
  MINING_MARK_X,
  ORE_SIZE,
  PANE_WIDTH,
} from "./pane-layout";
import { heapSlot } from "./heap-pile";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const baseSnap: TunnelSnapshot = {
  animation: "idle",
  facing: "east",
  frameIndex: 0,
  advance: 0,
  faceSwingProgress: 0,
  swingFraction: 0,
  digRate: 1,
  haulPhase: "none",
  haulProgress: 0,
  faceSlide: 1,
  crewSize: 1,
  heapLoads: 0,
};

function twoDwarfSnap(
  overrides: Omit<Partial<TunnelSnapshot>, "hauler"> & {
    hauler?: Partial<NonNullable<TunnelSnapshot["hauler"]>>;
  } = {},
): TunnelSnapshot {
  const { hauler: haulerOverrides, ...snapOverrides } = overrides;
  const defaultHauler = {
    animation: "walk" as const,
    facing: "east" as const,
    frameIndex: 0,
    phase: "out" as const,
    haulProgress: 0,
    pickupProgress: 0,
  };
  return {
    ...baseSnap,
    crewSize: 2,
    ...snapOverrides,
    hauler: { ...defaultHauler, ...haulerOverrides },
  };
}

function countDescendants(element: HTMLElement): number {
  return element.querySelectorAll("*").length;
}

function blockAtColumnIndex(
  host: HTMLElement,
  columnIndex: number,
): HTMLElement {
  const blocks = host.querySelectorAll<HTMLElement>(".pane-block");
  for (const block of blocks) {
    const left = Number(block.style.left.replace("px", ""));
    if (left / BLOCK_SIZE === columnIndex) {
      return block;
    }
  }
  throw new Error(`No column at index ${columnIndex}`);
}

function faceColumn(host: HTMLElement): HTMLElement {
  const face = host.querySelector<HTMLElement>("[data-face]");
  if (!face) {
    throw new Error("Face column not found");
  }
  return face;
}

function worldTransform(host: HTMLElement): string {
  const world = host.querySelector(".pane-tunnel-world") as HTMLElement;
  return world.style.transform;
}

function dwarfLeft(host: HTMLElement): number {
  const dwarf = host.querySelector<HTMLElement>("[data-dwarf]");
  if (!dwarf) {
    throw new Error("Dwarf not found");
  }
  return Number(dwarf.style.left.replace("px", ""));
}

function haulerLeft(host: HTMLElement): number {
  const hauler = host.querySelector<HTMLElement>("[data-hauler]");
  if (!hauler) {
    throw new Error("Hauler not found");
  }
  return Number(hauler.style.left.replace("px", ""));
}

function oreElements(host: HTMLElement): HTMLElement[] {
  return [...host.querySelectorAll<HTMLElement>("[data-ore]")];
}

function oreAtSlot(host: HTMLElement, slot: number): HTMLElement {
  const ore = host.querySelector<HTMLElement>(`[data-ore-slot="${slot}"]`);
  if (!ore) {
    throw new Error(`Ore at slot ${slot} not found`);
  }
  return ore;
}

describe("mountMiningTunnel", () => {
  it("never scrolls the world transform at any Advance", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    for (const advance of [0, 13, 100, 5000, 10000]) {
      tunnel.render({ ...baseSnap, advance });
      const transform = worldTransform(host);
      expect(
        transform === "" || transform === "translateX(0px)",
      ).toBe(true);
    }

    tunnel.destroy();
  });

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

  it("creates fifteen Mineable Block columns pinned on the block grid", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const world = host.querySelector(".pane-tunnel-world");
    expect(world).not.toBeNull();
    const columnsBeforeRender = world!.querySelectorAll(".pane-block");
    expect(columnsBeforeRender.length).toBe(MINING_TUNNEL_VISIBLE_COLUMNS);
    expect(MINING_TUNNEL_VISIBLE_COLUMNS).toBe(Math.ceil(PANE_WIDTH / BLOCK_SIZE));

    tunnel.render({ ...baseSnap, advance: 5000 });
    const columnsAfterRender = world!.querySelectorAll(".pane-block");
    expect(columnsAfterRender.length).toBe(MINING_TUNNEL_VISIBLE_COLUMNS);

    for (let i = 0; i < MINING_TUNNEL_VISIBLE_COLUMNS; i += 1) {
      if (i === 10) {
        expect(Number(faceColumn(host).style.left.replace("px", ""))).toBe(
          FACE_X,
        );
      } else {
        const col = blockAtColumnIndex(host, i);
        expect(col.style.left).toBe(`${i * BLOCK_SIZE}px`);
      }
    }

    tunnel.destroy();
  });

  it("does not mutate the DOM when rendering the same snapshot twice", async () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const snap = {
      ...baseSnap,
      advance: 50,
      haulPhase: "out" as const,
      haulProgress: 0.25,
      faceSlide: 0.5,
    };

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

  it("keeps the Face at FACE_X when faceSlide is settled", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    for (const advance of [0, 13, 100, 5000, 10000]) {
      tunnel.render({ ...baseSnap, advance, faceSlide: 1 });
      expect(Number(faceColumn(host).style.left.replace("px", ""))).toBe(
        FACE_X,
      );
    }

    tunnel.destroy();
  });

  it("slides the Face in from the east edge as faceSlide runs 0 to 1", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render({ ...baseSnap, advance: 5, faceSlide: 0 });
    expect(Number(faceColumn(host).style.left.replace("px", ""))).toBe(
      PANE_WIDTH,
    );

    tunnel.render({ ...baseSnap, advance: 5, faceSlide: 0.5 });
    expect(Number(faceColumn(host).style.left.replace("px", ""))).toBe(
      FACE_X + 0.5 * (PANE_WIDTH - FACE_X),
    );

    tunnel.render({ ...baseSnap, advance: 5, faceSlide: 1 });
    expect(Number(faceColumn(host).style.left.replace("px", ""))).toBe(FACE_X);

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
        faceSlide: 0.3,
      });
      expect(host.querySelectorAll(".pane-face-crack").length).toBeLessThanOrEqual(
        1,
      );
    }

    tunnel.destroy();
  });

  it("paints hollow west of FACE_X, Face at FACE_X, and solid east", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 10, faceSlide: 1 });

    expect(blockAtColumnIndex(host, 5).style.background).toBe("#1D1720");
    expect(faceColumn(host).style.background).toBe("#27A6A3");
    expect(blockAtColumnIndex(host, 11).style.background).toBe("#4A3B48");
    expect(blockAtColumnIndex(host, 14).style.background).toBe("#4A3B48");

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
      faceSlide: 0.6,
    });

    const face = faceColumn(host);
    expect(face.style.background).toBe("#176873");
    expect(face.querySelector(".pane-face-crack")).not.toBeNull();

    tunnel.destroy();
  });

  it("positions the floor band across the full Pane width", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 10 });

    const floor = host.querySelector<HTMLElement>(".pane-tunnel-floor");
    expect(floor).not.toBeNull();
    expect(floor!.style.left).toBe("0px");
    expect(floor!.style.width).toBe(`${PANE_WIDTH}px`);

    tunnel.destroy();
  });

  it("mounts a Cart placeholder on the floor at CART_X", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 0 });

    const cart = host.querySelector<HTMLElement>(".pane-cart");
    expect(cart).not.toBeNull();
    expect(cart!.style.left).toBe(`${CART_X}px`);
    expect(cart!.style.width).toBe(`${CART_WIDTH}px`);
    expect(cart!.style.height).toBe(`${CART_HEIGHT}px`);

    tunnel.destroy();
  });

  it("places the Dwarf at MINING_MARK_X when not hauling", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 3, haulPhase: "none", haulProgress: 0 });

    expect(dwarfLeft(host)).toBe(MINING_MARK_X);
    tunnel.destroy();
  });

  it("interpolates Dwarf left across the Haul path at worked progress values", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const cases: Array<{ haulProgress: number; expected: number }> = [
      { haulProgress: 0, expected: 258 },
      { haulProgress: 0.25, expected: 157 },
      { haulProgress: 0.5, expected: 56 },
      { haulProgress: 0.75, expected: 157 },
      { haulProgress: 1, expected: 258 },
    ];

    for (const { haulProgress, expected } of cases) {
      tunnel.render({
        ...baseSnap,
        advance: 1,
        haulPhase: haulProgress < 0.5 ? "out" : "back",
        haulProgress,
        faceSlide: 1,
      });
      expect(dwarfLeft(host)).toBe(expected);
    }

    expect(CART_MARK_X).toBe(56);
    expect(MINING_MARK_X).toBe(258);

    tunnel.destroy();
  });

  it("holds the Dwarf at MINING_MARK_X while the Face is sliding", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render({
      ...baseSnap,
      advance: 2,
      haulPhase: "out",
      haulProgress: 0.25,
      faceSlide: 0.2,
    });

    expect(dwarfLeft(host)).toBe(MINING_MARK_X);
    tunnel.destroy();
  });

  it("defines HAULER_MARK_X at 96 east of the Cart", () => {
    expect(HAULER_MARK_X).toBe(96);
    expect(HAULER_MARK_X).toBeGreaterThan(CART_X + CART_WIDTH);
    expect(dwarfLayout(HAULER_PACK)).toEqual(dwarfLayout(DWARF_PACK));
  });

  it("pins the Miner at MINING_MARK_X when a Hauler is present", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const cases = [
      { faceSlide: 1, haulProgress: 0 },
      { faceSlide: 1, haulProgress: 0.25 },
      { faceSlide: 1, haulProgress: 0.5 },
      { faceSlide: 1, haulProgress: 0.75 },
      { faceSlide: 1, haulProgress: 1 },
      { faceSlide: 0.2, haulProgress: 0.25 },
      { faceSlide: 0.5, haulProgress: 0.75 },
    ];

    for (const { faceSlide, haulProgress } of cases) {
      tunnel.render(
        twoDwarfSnap({
          advance: 1,
          faceSlide,
          hauler: {
            phase: haulProgress < 0.5 ? "out" : "back",
            haulProgress,
          },
        }),
      );
      expect(dwarfLeft(host)).toBe(MINING_MARK_X);
    }

    tunnel.destroy();
  });

  it("interpolates Hauler left across the lane at worked progress values", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const cases: Array<{ haulProgress: number; expected: number }> = [
      { haulProgress: 0, expected: 96 },
      { haulProgress: 0.25, expected: 76 },
      { haulProgress: 0.5, expected: 56 },
      { haulProgress: 0.75, expected: 76 },
      { haulProgress: 1, expected: 96 },
    ];

    for (const { haulProgress, expected } of cases) {
      tunnel.render(
        twoDwarfSnap({
          advance: 1,
          faceSlide: 1,
          hauler: {
            phase: haulProgress < 0.5 ? "out" : "back",
            haulProgress,
          },
        }),
      );
      expect(haulerLeft(host)).toBe(expected);
    }

    tunnel.destroy();
  });

  it("shuttles the Hauler from stand to pile and back during pickup", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const casesForLoads: Array<{
      heapLoads: number;
      cases: Array<{ pickupProgress: number; expected: number }>;
    }> = [
      {
        heapLoads: 1,
        cases: [
          { pickupProgress: 0, expected: 96 },
          { pickupProgress: 0.25, expected: 173 },
          { pickupProgress: 0.5, expected: 250 },
          { pickupProgress: 0.75, expected: 173 },
          { pickupProgress: 1, expected: 96 },
        ],
      },
      {
        heapLoads: 10,
        cases: [
          { pickupProgress: 0, expected: 96 },
          { pickupProgress: 0.25, expected: 119 },
          { pickupProgress: 0.5, expected: 142 },
          { pickupProgress: 0.75, expected: 119 },
          { pickupProgress: 1, expected: 96 },
        ],
      },
    ];

    for (const { heapLoads, cases } of casesForLoads) {
      for (const { pickupProgress, expected } of cases) {
        tunnel.render(
          twoDwarfSnap({
            advance: 1,
            heapLoads,
            hauler: { phase: "pickup", pickupProgress },
          }),
        );
        expect(haulerLeft(host)).toBe(expected);
      }
    }

    tunnel.destroy();
  });

  it("holds the Hauler at HAULER_MARK_X during pickup when the Heap is empty", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 0,
        hauler: { phase: "pickup", pickupProgress: 0.5 },
      }),
    );
    expect(haulerLeft(host)).toBe(HAULER_MARK_X);
    tunnel.destroy();
  });

  it("drops one Ore from the pile at the shuttle midpoint", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        hauler: { phase: "pickup", pickupProgress: 0.5 },
      }),
    );
    expect(oreElements(host).length).toBe(5);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        hauler: { phase: "pickup", pickupProgress: 0.75 },
      }),
    );
    expect(oreElements(host).length).toBe(4);
    tunnel.destroy();
  });

  it("renders carried Ore on the return leg of the shuttle only", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        hauler: { phase: "pickup", pickupProgress: 0.25 },
      }),
    );
    expect(host.querySelector("[data-ore-carried]")).toBeNull();

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        hauler: { phase: "pickup", pickupProgress: 0.75 },
      }),
    );
    expect(host.querySelectorAll("[data-ore-carried]").length).toBe(1);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 0,
        hauler: { phase: "pickup", pickupProgress: 0 },
      }),
    );
    expect(host.querySelector("[data-ore-carried]")).toBeNull();

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 3,
        hauler: { phase: "out", haulProgress: 0.25, pickupProgress: 0 },
      }),
    );
    expect(host.querySelector("[data-ore-carried]")).toBeNull();

    tunnel.destroy();
  });

  it("renders no Hauler sprite for a one-Dwarf Crew", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 3, crewSize: 1 });

    expect(host.querySelector("[data-hauler]")).toBeNull();
    tunnel.destroy();
  });

  it("styles the Hauler sprite like the Miner on the floor", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(twoDwarfSnap({ advance: 1 }));

    const dwarf = host.querySelector<HTMLImageElement>("[data-dwarf]")!;
    const hauler = host.querySelector<HTMLImageElement>("[data-hauler]")!;

    expect(hauler.style.bottom).toBe(dwarf.style.bottom);
    expect(hauler.style.imageRendering).toBe(dwarf.style.imageRendering);
    expect(hauler.draggable).toBe(dwarf.draggable);
    expect(hauler.width).toBe(dwarf.width);
    expect(hauler.height).toBe(dwarf.height);
    expect(hauler.style.width).toBe(dwarf.style.width);
    expect(hauler.style.height).toBe(dwarf.style.height);

    tunnel.destroy();
  });

  it("does not mutate the DOM when rendering the same two-Dwarf snapshot twice", async () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const snap = twoDwarfSnap({
      advance: 50,
      faceSlide: 0.5,
      heapLoads: 5,
      hauler: {
        phase: "pickup",
        pickupProgress: 0.35,
        frameIndex: 2,
      },
    });

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

  it("resolves Miner and Hauler walk frames from different packs", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(
      twoDwarfSnap({
        advance: 1,
        animation: "walk",
        facing: "east",
        hauler: { animation: "walk", facing: "east" },
      }),
    );

    const dwarf = host.querySelector<HTMLImageElement>("[data-dwarf]")!;
    const hauler = host.querySelector<HTMLImageElement>("[data-hauler]")!;

    expect(dwarf.src).toMatch(/\/assets\/characters\/dwarf\//);
    expect(hauler.src).toMatch(/\/assets\/characters\/hauler\//);
    expect(dwarf.src).not.toBe(hauler.src);

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

  it("renders one Ore per heapLoads behind both Dwarves for a two-Dwarf Crew", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(twoDwarfSnap({ heapLoads: 3 }));

    const heap = host.querySelector(".pane-heap");
    expect(heap).not.toBeNull();

    const ores = oreElements(host);
    expect(ores.length).toBe(3);

    for (let i = 0; i < 3; i += 1) {
      const ore = oreAtSlot(host, i);
      const { left, bottom } = heapSlot(i);
      expect(ore.style.left).toBe(`${left}px`);
      expect(ore.style.bottom).toBe(`${bottom}px`);
      expect(ore.style.width).toBe(`${ORE_SIZE}px`);
      expect(ore.style.height).toBe(`${ORE_SIZE}px`);
      expect(ore.style.background).toBe("#27A6A3");
    }

    const css = readFileSync(resolve("src/styles.css"), "utf8");
    expect(css).toMatch(/\.pane-heap\s*\{[^}]*z-index:\s*3/);
    expect(css).toMatch(/\.pane-cart\s*\{[^}]*z-index:\s*4/);
    expect(css).toMatch(/\.pane-dwarf\s*\{[^}]*z-index:\s*5/);

    tunnel.destroy();
  });

  it("renders no Ore for a one-Dwarf Crew regardless of heapLoads", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 3, crewSize: 1, heapLoads: 5 });

    expect(host.querySelector(".pane-heap")).toBeNull();
    expect(oreElements(host).length).toBe(0);
    tunnel.destroy();
  });

  it("removes highest-index Ore first when heapLoads shrinks", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(twoDwarfSnap({ heapLoads: 3 }));
    tunnel.render(twoDwarfSnap({ heapLoads: 2 }));

    const ores = oreElements(host);
    expect(ores.length).toBe(2);
    expect(oreAtSlot(host, 0)).not.toBeNull();
    expect(oreAtSlot(host, 1)).not.toBeNull();
    expect(host.querySelector("[data-ore-slot=\"2\"]")).toBeNull();

    tunnel.destroy();
  });

  it("does not mutate the DOM when rendering the same two-Dwarf heap snapshot twice", async () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const snap = twoDwarfSnap({ advance: 10, heapLoads: 4 });

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
});

// @vitest-environment happy-dom

import { describe, expect, it } from "vitest";
import { faceDamageState, mountMiningTunnel } from "./mining-tunnel";
import { tunnelArtContentBottomGap, tunnelArtKeysUnder, tunnelArtPath } from "../data/tunnel-art-pack";
import { TUNNEL_ART_PACK, tunnelArtUrl } from "./tunnel-art";
import type { TunnelSnapshot } from "./mine-presenter";
import { dwarfLayout } from "../data/external-sprite-pack";
import { DWARF_PACK } from "./dwarf-frames";
import { HAULER_PACK } from "./hauler-frames";
import { heapCapacityFor } from "../core/mining-engine";
import {
  CART_HEIGHT,
  CART_MARK_X,
  CART_WIDTH,
  CART_X,
  FACE_X,
  HAULER_MARK_X,
  MINING_MARK_X,
  ORE_SIZE,
  PANE_HEIGHT,
  PANE_WIDTH,
} from "./pane-layout";
import { fallingOrePosition, heapSlot } from "./heap-pile";
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
  fallingOre: [],
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

function faceTileBackground(state: string): string {
  const path = tunnelArtPath(TUNNEL_ART_PACK, `tiles/face/${state}`);
  return `url("${tunnelArtUrl(path)}")`;
}

const HEAP_ORE_KEYS = tunnelArtKeysUnder(TUNNEL_ART_PACK, "objects/ore/gold-");

function heapOreObjectBackground(artKey: string): string {
  const path = tunnelArtPath(TUNNEL_ART_PACK, artKey);
  return `url("${tunnelArtUrl(path)}")`;
}

function adjustedHeapOreBottom(slotBottom: number, artKey: string): number {
  return (
    slotBottom -
    tunnelArtContentBottomGap(TUNNEL_ART_PACK, artKey, ORE_SIZE)
  );
}

describe("faceDamageState", () => {
  it("maps worked progress boundaries to damage quarters", () => {
    expect(faceDamageState(0)).toBe("intact");
    expect(faceDamageState(0.25)).toBe("chipped");
    expect(faceDamageState(0.4999)).toBe("chipped");
    expect(faceDamageState(0.5)).toBe("cracked");
    expect(faceDamageState(0.75)).toBe("crumbling");
    expect(faceDamageState(1)).toBe("crumbling");
  });

  it("throws when progress is outside 0…1", () => {
    expect(() => faceDamageState(-0.01)).toThrow();
    expect(() => faceDamageState(1.01)).toThrow();
  });
});

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

  it("draws the tunnel interior background and a single Face column", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const world = host.querySelector<HTMLElement>(".pane-tunnel-world");
    expect(world).not.toBeNull();
    const backgroundPath = tunnelArtPath(
      TUNNEL_ART_PACK,
      "background/tunnel-interior",
    );
    const backgroundUrl = tunnelArtUrl(backgroundPath);
    expect(world!.style.backgroundImage).toBe(`url("${backgroundUrl}")`);
    expect(world!.style.backgroundSize).toBe(`${PANE_WIDTH}px ${PANE_HEIGHT}px`);
    expect(world!.style.imageRendering).toBe("pixelated");

    const columnsBeforeRender = world!.querySelectorAll(".pane-block");
    expect(columnsBeforeRender.length).toBe(1);

    tunnel.render({ ...baseSnap, advance: 5000 });
    const columnsAfterRender = world!.querySelectorAll(".pane-block");
    expect(columnsAfterRender.length).toBe(1);
    expect(Number(faceColumn(host).style.left.replace("px", ""))).toBe(FACE_X);

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

  it("paints the Face from tiles without a crack overlay", () => {
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
      expect(host.querySelectorAll(".pane-face-crack").length).toBe(0);
    }

    tunnel.destroy();
  });

  it("does not paint retired hollow or floor colors on any element", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({ ...baseSnap, advance: 10, faceSlide: 1 });

    for (const element of host.querySelectorAll<HTMLElement>("*")) {
      expect(element.style.background).not.toBe("#1D1720");
      expect(element.style.background).not.toBe("#3B2F3A");
      expect(element.style.background).not.toBe("#176873");
      expect(element.style.background).not.toBe("#72E2D2");
    }
    expect(faceColumn(host).style.backgroundImage).toBe(
      faceTileBackground("intact"),
    );
    expect(host.querySelector(".pane-tunnel-floor")).toBeNull();

    tunnel.destroy();
  });

  it("paints the Face column from the damage-quarter tile", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    const quarters: Array<{
      state: string;
      faceSwingProgress: number;
      swingFraction: number;
    }> = [
      { state: "intact", faceSwingProgress: 0, swingFraction: 0 },
      { state: "chipped", faceSwingProgress: 250, swingFraction: 0 },
      { state: "cracked", faceSwingProgress: 500, swingFraction: 0 },
      { state: "crumbling", faceSwingProgress: 750, swingFraction: 0 },
      { state: "crumbling", faceSwingProgress: 1000, swingFraction: 0 },
    ];

    for (const { state, faceSwingProgress, swingFraction } of quarters) {
      tunnel.render({
        ...baseSnap,
        advance: 0,
        faceSwingProgress,
        swingFraction,
        faceSlide: 0.6,
      });

      const face = faceColumn(host);
      expect(face.style.backgroundImage).toBe(faceTileBackground(state));
      expect(face.style.backgroundRepeat).toBe("repeat-y");
      expect(face.style.backgroundSize).toBe("48px 48px");
      expect(face.style.imageRendering).toBe("pixelated");
      expect(face.querySelector(".pane-face-crack")).toBeNull();
    }

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
      { haulProgress: 0, expected: 354 },
      { haulProgress: 0.25, expected: 253 },
      { haulProgress: 0.5, expected: 152 },
      { haulProgress: 0.75, expected: 253 },
      { haulProgress: 1, expected: 354 },
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

    expect(CART_MARK_X).toBe(152);
    expect(MINING_MARK_X).toBe(354);

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

  it("defines HAULER_MARK_X east of the Cart mark", () => {
    expect(HAULER_MARK_X).toBe(192);
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
      { haulProgress: 0, expected: 192 },
      { haulProgress: 0.25, expected: 172 },
      { haulProgress: 0.5, expected: 152 },
      { haulProgress: 0.75, expected: 172 },
      { haulProgress: 1, expected: 192 },
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

  const pickupExcursionCases: Array<{ pickupProgress: number; expected: number }> = [
    { pickupProgress: 0, expected: HAULER_MARK_X },
    { pickupProgress: 0.25, expected: 257 },
    { pickupProgress: 0.5, expected: 322 },
    { pickupProgress: 0.75, expected: 257 },
    { pickupProgress: 1, expected: HAULER_MARK_X },
  ];

  it("shuttles the Hauler on a fixed 130 px excursion at partial Heap depth", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    for (const { pickupProgress, expected } of pickupExcursionCases) {
      tunnel.render(
        twoDwarfSnap({
          advance: 1,
          heapLoads: 5,
          hauler: { phase: "pickup", pickupProgress },
        }),
      );
      expect(haulerLeft(host)).toBe(expected);
    }

    tunnel.destroy();
  });

  it("shuttles the Hauler on the same fixed excursion at full Heap capacity", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const fullHeap = heapCapacityFor(0);

    for (const { pickupProgress, expected } of pickupExcursionCases) {
      tunnel.render(
        twoDwarfSnap({
          advance: 1,
          heapLoads: fullHeap,
          hauler: { phase: "pickup", pickupProgress },
        }),
      );
      expect(haulerLeft(host)).toBe(expected);
    }

    tunnel.destroy();
  });

  it("aligns carried Ore with the Hauler on the pickup return leg", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: heapCapacityFor(0),
        hauler: { phase: "pickup", pickupProgress: 0.75 },
      }),
    );

    const hauler = host.querySelector<HTMLElement>("[data-hauler]")!;
    const carried = host.querySelector<HTMLElement>("[data-ore-carried]")!;
    expect(carried).not.toBeNull();
    expect(carried!.style.left).toBe(hauler.style.left);

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
      const artKey = HEAP_ORE_KEYS[i % HEAP_ORE_KEYS.length]!;
      const { left, bottom } = heapSlot(i);
      expect(ore.style.left).toBe(`${left}px`);
      expect(ore.style.bottom).toBe(
        `${adjustedHeapOreBottom(bottom, artKey)}px`,
      );
      expect(ore.style.width).toBe(`${ORE_SIZE}px`);
      expect(ore.style.height).toBe(`${ORE_SIZE}px`);
      expect(ore.style.backgroundImage).toBe(heapOreObjectBackground(artKey));
      expect(ore.style.imageRendering).toBe("pixelated");
    }

    const css = readFileSync(resolve("src/styles.css"), "utf8");
    expect(css).toMatch(/\.pane-heap\s*\{[^}]*z-index:\s*3/);
    expect(css).toMatch(/\.pane-cart\s*\{[^}]*z-index:\s*4/);
    expect(css).toMatch(/\.pane-dwarf\s*\{[^}]*z-index:\s*5/);

    tunnel.destroy();
  });

  it("paints settled Heap chunks from the art pack with stable variants", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(twoDwarfSnap({ heapLoads: 3 }));

    const variants = HEAP_ORE_KEYS.slice(0, 3);
    for (const [slot, artKey] of variants.entries()) {
      const ore = oreAtSlot(host, slot);
      expect(ore.dataset["oreVariant"]).toBe(artKey);
      expect(ore.dataset["oreVariant"]!.startsWith("objects/ore/gold-")).toBe(
        true,
      );
      expect(ore.style.backgroundImage).toBe(heapOreObjectBackground(artKey));
      expect(ore.style.backgroundImage.length).toBeGreaterThan(0);
    }

    tunnel.destroy();
  });

  it("paints the carried chunk with the variant of the westmost lifted slot", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 4,
        hauler: { phase: "pickup", pickupProgress: 0.75 },
      }),
    );

    const carried = host.querySelector<HTMLElement>("[data-ore-carried]");
    const artKey = HEAP_ORE_KEYS[3]!;
    expect(carried).not.toBeNull();
    expect(carried!.dataset["oreVariant"]).toBe(artKey);
    expect(carried!.style.backgroundImage).toBe(heapOreObjectBackground(artKey));

    tunnel.destroy();
  });

  it("bottom-aligns heap objects by content_box so contents rest on the floor", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(twoDwarfSnap({ heapLoads: 6 }));

    const largeBSlot = 1;
    const smallSlot = 5;
    const largeBKey = HEAP_ORE_KEYS[largeBSlot]!;
    const smallKey = HEAP_ORE_KEYS[smallSlot]!;
    expect(largeBKey).toBe("objects/ore/gold-large-b");
    expect(smallKey).toBe("objects/ore/gold-small");

    const largeB = oreAtSlot(host, largeBSlot);
    const small = oreAtSlot(host, smallSlot);
    const largeBSlotBottom = heapSlot(largeBSlot).bottom;
    const smallSlotBottom = heapSlot(smallSlot).bottom;

    expect(Number(largeB.style.bottom.replace("px", ""))).toBe(
      largeBSlotBottom -
        tunnelArtContentBottomGap(TUNNEL_ART_PACK, largeBKey, ORE_SIZE),
    );
    expect(Number(small.style.bottom.replace("px", ""))).toBe(
      smallSlotBottom -
        tunnelArtContentBottomGap(TUNNEL_ART_PACK, smallKey, ORE_SIZE),
    );
    expect(
      tunnelArtContentBottomGap(TUNNEL_ART_PACK, smallKey, ORE_SIZE),
    ).toBe(10);
    expect(
      tunnelArtContentBottomGap(TUNNEL_ART_PACK, largeBKey, ORE_SIZE),
    ).toBe(1);

    tunnel.destroy();
  });

  it("renders a transient bag-bound fall for a one-Dwarf Crew", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({
      ...baseSnap,
      advance: 3,
      fallingOre: [{ destination: "bag", slot: 0, progress: 0.5 }],
    });

    expect(host.querySelector(".pane-heap")).toBeNull();
    const ores = oreElements(host);
    expect(ores.length).toBe(1);
    const fallingPos = fallingOrePosition("bag", 0, 0.5);
    const artKey = HEAP_ORE_KEYS[0]!;
    expect(ores[0]!.style.left).toBe(`${fallingPos.left}px`);
    expect(ores[0]!.style.bottom).toBe(
      `${adjustedHeapOreBottom(fallingPos.bottom, artKey)}px`,
    );
    expect(ores[0]!.dataset["oreSlot"]).toBeUndefined();

    tunnel.render({
      ...baseSnap,
      advance: 3,
      fallingOre: [],
    });
    expect(oreElements(host).length).toBe(0);

    tunnel.destroy();
  });

  it("renders no Ore for a one-Dwarf Crew when nothing is falling", () => {
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

  it("positions a falling Ore at fallingOrePosition and settled neighbours at heapSlot", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 2,
        fallingOre: [{ destination: "heap", slot: 1, progress: 0.5 }],
      }),
    );

    const falling = oreAtSlot(host, 1);
    const settled = oreAtSlot(host, 0);
    const fallingPos = fallingOrePosition("heap", 1, 0.5);
    const settledPos = heapSlot(0);
    const fallingKey = HEAP_ORE_KEYS[1]!;
    const settledKey = HEAP_ORE_KEYS[0]!;
    expect(falling.style.left).toBe(`${fallingPos.left}px`);
    expect(falling.style.bottom).toBe(
      `${adjustedHeapOreBottom(fallingPos.bottom, fallingKey)}px`,
    );
    expect(settled.style.left).toBe(`${settledPos.left}px`);
    expect(settled.style.bottom).toBe(
      `${adjustedHeapOreBottom(settledPos.bottom, settledKey)}px`,
    );

    tunnel.destroy();
  });

  it("does not mutate the DOM when rendering the same fallingOre snapshot twice", async () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const snap = twoDwarfSnap({
      heapLoads: 2,
      fallingOre: [{ destination: "heap", slot: 1, progress: 0.25 }],
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

  it("re-renders when only a fallingOre progress value changes", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 1,
        fallingOre: [{ destination: "heap", slot: 0, progress: 0.25 }],
      }),
    );
    const before = oreAtSlot(host, 0).style.bottom;

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 1,
        fallingOre: [{ destination: "heap", slot: 0, progress: 0.75 }],
      }),
    );
    const after = oreAtSlot(host, 0).style.bottom;

    expect(after).not.toBe(before);
    tunnel.destroy();
  });
});

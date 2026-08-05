// @vitest-environment happy-dom

import { describe, expect, it } from "vitest";
import { faceDamageState, mountMiningTunnel } from "./mining-tunnel";
import { tunnelArtContentBottomGap, tunnelArtPath } from "../data/tunnel-art-pack";
import { TUNNEL_ART_PACK, tunnelArtUrl } from "./tunnel-art";
import type { HeapOreSnapshot, TunnelSnapshot } from "./mine-presenter";
import { createMinePresenter } from "./mine-presenter";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot } from "../core/mining-engine";
import { dwarfLayout } from "../data/external-sprite-pack";
import { DWARF_PACK } from "./dwarf-frames";
import { HAULER_PACK } from "./hauler-frames";
import { heapCapacityFor } from "../core/mining-engine";
import {
  CART_HEIGHT,
  CART_MARK_X,
  CART_WIDTH,
  CART_X,
  DWARF_FRAME_W,
  DWARF_SCALE,
  FACE_X,
  FLOOR_Y,
  HAULER_HAND_DX,
  HAULER_MARK_X,
  MINING_MARK_X,
  ORE_SIZE,
  PANE_HEIGHT,
  PANE_WIDTH,
} from "./pane-layout";
import { fallingOrePosition } from "./heap-pile";
import { heapOreArtKey } from "./heap-ore-variants";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const baseSnap: TunnelSnapshot = {
  animation: "idle",
  facing: "east",
  frameIndex: 0,
  advance: 0,
  faceSwingProgress: 0,
  swingFraction: 0,
  pickDamage: 1,
  digRate: 1,
  haulPhase: "none",
  haulProgress: 0,
  faceSlide: 1,
  crewSize: 1,
  heapLoads: 0,
  heapOre: [],
  fallingOre: [],
};

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
    left: HAULER_MARK_X,
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

function oreById(host: HTMLElement, id: number): HTMLElement {
  const ore = host.querySelector<HTMLElement>(`[data-ore-id="${id}"]`);
  if (!ore) {
    throw new Error(`Ore with id ${id} not found`);
  }
  return ore;
}

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

function twoDwarfHeapOre(count: number): HeapOreSnapshot[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    left: 400 - i * 36,
    bottom: 8 + (i % 3) * 12,
    variantIndex: i % 6,
  }));
}

function faceTileBackground(state: string): string {
  const path = tunnelArtPath(TUNNEL_ART_PACK, `tiles/face/${state}`);
  return `url("${tunnelArtUrl(path)}")`;
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

  it("stands the Miner, Hauler, and Cart on FLOOR_Y", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(twoDwarfSnap({ advance: 1 }));

    const cart = host.querySelector<HTMLElement>(".pane-cart")!;
    const dwarf = host.querySelector<HTMLElement>("[data-dwarf]")!;
    const hauler = host.querySelector<HTMLElement>("[data-hauler]")!;
    const floorBottom = `${FLOOR_Y}px`;

    expect(FLOOR_Y).toBe(8);
    expect(cart.style.bottom).toBe(floorBottom);
    expect(dwarf.style.bottom).toBe(floorBottom);
    expect(hauler.style.bottom).toBe(floorBottom);

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

  it("uses hauler.left for pickup-phase positioning", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const pickupLeft = 301;

    tunnel.render(
      twoDwarfSnap({
        advance: 1,
        heapLoads: 5,
        hauler: { phase: "pickup", pickupProgress: 0.25, left: pickupLeft },
      }),
    );
    expect(haulerLeft(host)).toBe(pickupLeft);

    tunnel.destroy();
  });

  it("anchors the carried Load to the Hauler's hands facing east", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const haulerX = 301;

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        heapOre: twoDwarfHeapOre(4),
        carriedVariantIndexes: [2],
        hauler: { phase: "pickup", pickupProgress: 0.75, facing: "east", left: haulerX },
      }),
    );

    const hauler = host.querySelector<HTMLElement>("[data-hauler]")!;
    const carried = host.querySelector<HTMLElement>("[data-ore-carried]")!;
    expect(Number(hauler.style.left.replace("px", ""))).toBe(haulerX);
    expect(carried.style.left).toBe(`${haulerX + HAULER_HAND_DX}px`);

    tunnel.destroy();
  });

  it("mirrors the carried Load hand anchor when the Hauler faces west", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const haulerX = 301;
    const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
    const westHandDx = dwarfW - ORE_SIZE - HAULER_HAND_DX;

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        heapOre: twoDwarfHeapOre(4),
        carriedVariantIndexes: [2],
        hauler: { phase: "pickup", pickupProgress: 0.75, facing: "west", left: haulerX },
      }),
    );

    const hauler = host.querySelector<HTMLElement>("[data-hauler]")!;
    const carried = host.querySelector<HTMLElement>("[data-ore-carried]")!;
    expect(Number(hauler.style.left.replace("px", ""))).toBe(haulerX);
    expect(westHandDx).toBe(6);
    expect(carried.style.left).toBe(`${haulerX + westHandDx}px`);

    tunnel.destroy();
  });

  it("paints the carried Load above the Hauler sprite", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 4,
        heapOre: twoDwarfHeapOre(3),
        carriedVariantIndexes: [1],
        hauler: { phase: "pickup", pickupProgress: 0.75, left: 301 },
      }),
    );

    const carried = host.querySelector<HTMLElement>("[data-ore-carried]")!;
    expect(carried.classList.contains("pane-ore-carried")).toBe(true);

    const css = readFileSync(resolve("src/styles.css"), "utf8");
    expect(css).toMatch(/\.pane-ore-carried\s*\{[^}]*z-index:\s*6/);

    tunnel.destroy();
  });

  it("aligns carried Ore with the Hauler on the pickup return leg", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const loads = heapCapacityFor(0);
    const haulerX = 301;

    tunnel.render(
      twoDwarfSnap({
        heapLoads: loads,
        heapOre: twoDwarfHeapOre(loads),
        carriedVariantIndexes: [2],
        hauler: { phase: "pickup", pickupProgress: 0.75, left: haulerX },
      }),
    );

    const hauler = host.querySelector<HTMLElement>("[data-hauler]")!;
    const carried = host.querySelector<HTMLElement>("[data-ore-carried]")!;
    expect(carried).not.toBeNull();
    expect(carried!.style.left).toBe(
      `${Number(hauler.style.left.replace("px", "")) + HAULER_HAND_DX}px`,
    );

    tunnel.destroy();
  });

  it("holds the Hauler at HAULER_MARK_X during pickup when the Heap is empty", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 0,
        hauler: { phase: "pickup", pickupProgress: 0.5, left: HAULER_MARK_X },
      }),
    );
    expect(haulerLeft(host)).toBe(HAULER_MARK_X);
    tunnel.destroy();
  });

  it("drops one Ore from the pile at the Lift midpoint", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const heap5 = twoDwarfHeapOre(5);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        heapOre: heap5,
        hauler: { phase: "pickup", pickupProgress: 0.5, left: 301 },
      }),
    );
    expect(oreElements(host).length).toBe(5);
    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        heapOre: heap5.slice(0, 4),
        carriedVariantIndexes: [4],
        hauler: { phase: "pickup", pickupProgress: 0.75, left: 301 },
      }),
    );
    expect(oreElements(host).length).toBe(4);
    tunnel.destroy();
  });

  it("renders carried Ore only after the Lift midpoint", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const heap5 = twoDwarfHeapOre(5);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        heapOre: heap5,
        hauler: { phase: "pickup", pickupProgress: 0.25, left: 257 },
      }),
    );
    expect(host.querySelector("[data-ore-carried]")).toBeNull();

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 5,
        heapOre: heap5.slice(0, 4),
        carriedVariantIndexes: [4],
        hauler: { phase: "pickup", pickupProgress: 0.75, left: 301 },
      }),
    );
    expect(host.querySelectorAll("[data-ore-carried]").length).toBe(1);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 0,
        heapOre: [],
        hauler: { phase: "pickup", pickupProgress: 0, left: HAULER_MARK_X },
      }),
    );
    expect(host.querySelector("[data-ore-carried]")).toBeNull();

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 3,
        heapOre: twoDwarfHeapOre(3),
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
      heapOre: twoDwarfHeapOre(5),
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

  it("renders one element per heapOre entry behind both Dwarves for a two-Dwarf Crew", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const heapOre = twoDwarfHeapOre(3);
    tunnel.render(twoDwarfSnap({ heapLoads: 3, heapOre }));

    const heap = host.querySelector(".pane-heap");
    expect(heap).not.toBeNull();

    const ores = oreElements(host);
    expect(ores.length).toBe(3);

    for (const entry of heapOre) {
      const ore = oreById(host, entry.id);
      const artKey = heapOreArtKey(entry.variantIndex);
      expect(ore.style.left).toBe(`${entry.left}px`);
      expect(ore.style.bottom).toBe(`${entry.bottom}px`);
      expect(ore.style.width).toBe(`${ORE_SIZE}px`);
      expect(ore.style.height).toBe(`${ORE_SIZE}px`);
      expect(ore.style.backgroundImage).toBe(heapOreObjectBackground(artKey));
      expect(ore.style.imageRendering).toBe("pixelated");
      expect(ore.dataset["oreId"]).toBe(String(entry.id));
    }

    const css = readFileSync(resolve("src/styles.css"), "utf8");
    expect(css).toMatch(/\.pane-heap\s*\{[^}]*z-index:\s*3/);
    expect(css).toMatch(/\.pane-cart\s*\{[^}]*z-index:\s*4/);
    expect(css).toMatch(/\.pane-dwarf\s*\{[^}]*z-index:\s*5/);

    tunnel.destroy();
  });

  it("keys heap elements by body id and preserves surviving nodes when the middle id is removed", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const three = [
      { id: 10, left: 400, bottom: 8, variantIndex: 0 },
      { id: 20, left: 364, bottom: 8, variantIndex: 1 },
      { id: 30, left: 328, bottom: 8, variantIndex: 2 },
    ];
    tunnel.render(twoDwarfSnap({ heapLoads: 3, heapOre: three }));

    const first = oreById(host, 10);
    const third = oreById(host, 30);
    const firstVariant = first.dataset["oreVariant"];
    const thirdVariant = third.dataset["oreVariant"];

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 2,
        heapOre: [three[0]!, three[2]!],
      }),
    );

    expect(oreById(host, 10)).toBe(first);
    expect(oreById(host, 30)).toBe(third);
    expect(first.dataset["oreVariant"]).toBe(firstVariant);
    expect(third.dataset["oreVariant"]).toBe(thirdVariant);
    expect(host.querySelector("[data-ore-id=\"20\"]")).toBeNull();

    tunnel.destroy();
  });

  it("paints settled Heap chunks from heapOreArtKey with stable variants", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const heapOre = [
      { id: 1, left: 400, bottom: 8, variantIndex: 0 },
      { id: 2, left: 364, bottom: 8, variantIndex: 1 },
      { id: 3, left: 328, bottom: 8, variantIndex: 2 },
    ];
    tunnel.render(twoDwarfSnap({ heapLoads: 3, heapOre }));

    for (const entry of heapOre) {
      const ore = oreById(host, entry.id);
      const artKey = heapOreArtKey(entry.variantIndex);
      expect(ore.dataset["oreVariant"]).toBe(artKey);
      expect(ore.dataset["oreVariant"]!.startsWith("objects/ore/gold-")).toBe(
        true,
      );
      expect(ore.style.backgroundImage).toBe(heapOreObjectBackground(artKey));
      expect(ore.style.backgroundImage.length).toBeGreaterThan(0);
    }

    tunnel.destroy();
  });

  it("paints the carried chunk with carriedVariantIndexes", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const variantIndex = 3;
    const artKey = heapOreArtKey(variantIndex);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 4,
        heapOre: twoDwarfHeapOre(3),
        carriedVariantIndexes: [variantIndex],
        hauler: { phase: "pickup", pickupProgress: 0.75, left: 301 },
      }),
    );

    const carried = host.querySelector<HTMLElement>("[data-ore-carried]");
    expect(carried).not.toBeNull();
    expect(carried!.dataset["oreVariant"]).toBe(artKey);
    expect(carried!.style.backgroundImage).toBe(heapOreObjectBackground(artKey));

    tunnel.destroy();
  });

  it("shows the carried element only when carriedVariantIndexes is present", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 3,
        heapOre: twoDwarfHeapOre(3),
        hauler: { phase: "pickup", pickupProgress: 0.25, left: 257 },
      }),
    );
    expect(host.querySelector("[data-ore-carried]")).toBeNull();

    tunnel.render(
      twoDwarfSnap({
        heapLoads: 3,
        heapOre: twoDwarfHeapOre(2),
        carriedVariantIndexes: [1],
        hauler: { phase: "pickup", pickupProgress: 0.75, left: 301 },
      }),
    );
    expect(host.querySelectorAll("[data-ore-carried]").length).toBe(1);

    tunnel.destroy();
  });

  it("renders a transient bag-bound fall for a one-Dwarf Crew", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({
      ...baseSnap,
      advance: 3,
      fallingOre: [{ slot: 0, progress: 0.5 }],
    });

    expect(host.querySelector(".pane-heap")).toBeNull();
    const ores = oreElements(host);
    expect(ores.length).toBe(1);
    const fallingPos = fallingOrePosition(0, 0.5);
    const artKey = heapOreArtKey(0);
    expect(ores[0]!.style.left).toBe(`${fallingPos.left}px`);
    expect(ores[0]!.style.bottom).toBe(
      `${adjustedHeapOreBottom(fallingPos.bottom, artKey)}px`,
    );
    expect(ores[0]!.dataset["oreId"]).toBeUndefined();

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

  it("removes elements when heapOre entries disappear", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const three = twoDwarfHeapOre(3);
    tunnel.render(twoDwarfSnap({ heapLoads: 3, heapOre: three }));
    tunnel.render(twoDwarfSnap({ heapLoads: 2, heapOre: three.slice(0, 2) }));

    const ores = oreElements(host);
    expect(ores.length).toBe(2);
    expect(oreById(host, 1)).not.toBeNull();
    expect(oreById(host, 2)).not.toBeNull();
    expect(host.querySelector("[data-ore-id=\"3\"]")).toBeNull();

    tunnel.destroy();
  });

  it("does not mutate the DOM when rendering the same two-Dwarf heap snapshot twice", async () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const snap = twoDwarfSnap({
      advance: 10,
      heapLoads: 4,
      heapOre: twoDwarfHeapOre(4),
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

  it("re-renders when heapOre position changes but not when only heapLoads changes", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const heapOre = twoDwarfHeapOre(3);
    tunnel.render(twoDwarfSnap({ heapLoads: 3, heapOre }));

    const before = oreById(host, 1).style.left;
    const moved = heapOre.map((entry) =>
      entry.id === 1 ? { ...entry, left: entry.left - 5 } : entry,
    );
    tunnel.render(twoDwarfSnap({ heapLoads: 3, heapOre: moved }));
    expect(oreById(host, 1).style.left).not.toBe(before);

    const afterMove = oreById(host, 1).style.left;
    tunnel.render(twoDwarfSnap({ heapLoads: 99, heapOre: moved }));
    expect(oreById(host, 1).style.left).toBe(afterMove);

    tunnel.destroy();
  });

  it("positions pile elements at heapOre left and bottom without content-box adjustment", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 5,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    const snap = presenter.snapshot();
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render(snap);

    for (const entry of snap.heapOre) {
      const ore = oreById(host, entry.id);
      expect(ore.style.left).toBe(`${entry.left}px`);
      expect(ore.style.bottom).toBe(`${entry.bottom}px`);
    }

    tunnel.destroy();
  });

  it("renders the one-Dwarf bag fall at the same worked positions as before", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    tunnel.render({
      ...baseSnap,
      advance: 3,
      fallingOre: [{ slot: 0, progress: 0.5 }],
    });

    const ores = oreElements(host);
    const fallingPos = fallingOrePosition(0, 0.5);
    const artKey = heapOreArtKey(0);
    expect(ores[0]!.style.left).toBe(`${fallingPos.left}px`);
    expect(ores[0]!.style.bottom).toBe(
      `${adjustedHeapOreBottom(fallingPos.bottom, artKey)}px`,
    );

    tunnel.destroy();
  });
});

/** Pane mining Tunnel: fixed-camera arena, Cart, Dwarf Haul travel, Face slide-in.

Composition from [Prototype the mining scene at 480x112](#318): full-band Tunnel,
Colony corner chip, cyan Face, no Dig Rate / Ore / Ingots on the Pane.
*/
import type { TunnelSnapshot } from "./mine-presenter";
import { hardnessFor } from "../core/mining-engine";
import { dwarfLayout, type ExternalSpritePack } from "../data/external-sprite-pack";
import { DWARF_PACK, dwarfFrameUrlsFor } from "./dwarf-frames";
import { HAULER_PACK, haulerFrameUrlsFor } from "./hauler-frames";
import { fallingOrePosition, haulerPickupTargetX, heapSlot } from "./heap-pile";
import {
  BLOCK_SIZE,
  CART_HEIGHT,
  CART_MARK_X,
  CART_WIDTH,
  CART_X,
  DWARF_SCALE,
  FACE_X,
  HAULER_MARK_X,
  MINING_MARK_X,
  ORE_SIZE,
  PANE_HEIGHT,
  PANE_WIDTH,
} from "./pane-layout";

export interface MiningTunnelView {
  root: HTMLElement;
  render(snap: TunnelSnapshot): void;
  destroy(): void;
}

const SOLID = "#4A3B48";
const HOLLOW = "#1D1720";
const FACE = "#27A6A3";
const FACE_DEEP = "#176873";
const CRACK = "#72E2D2";
const FLOOR = "#3B2F3A";
const CART_FILL = "#5C4A58";

const VISIBLE_COLUMNS = Math.ceil(PANE_WIDTH / BLOCK_SIZE);
const FACE_COLUMN_INDEX = Math.floor(FACE_X / BLOCK_SIZE);

export const MINING_TUNNEL_VISIBLE_COLUMNS = VISIBLE_COLUMNS;

function haulerFieldsEqual(
  a: TunnelSnapshot["hauler"],
  b: TunnelSnapshot["hauler"],
): boolean {
  if (a === undefined && b === undefined) {
    return true;
  }
  if (a === undefined || b === undefined) {
    return false;
  }
  return (
    a.animation === b.animation &&
    a.facing === b.facing &&
    a.frameIndex === b.frameIndex &&
    a.phase === b.phase &&
    a.haulProgress === b.haulProgress &&
    a.pickupProgress === b.pickupProgress
  );
}

function fallingOreEqual(
  a: TunnelSnapshot["fallingOre"],
  b: TunnelSnapshot["fallingOre"],
): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i += 1) {
    if (a[i]!.slot !== b[i]!.slot || a[i]!.progress !== b[i]!.progress) {
      return false;
    }
  }
  return true;
}

function snapEquals(a: TunnelSnapshot, b: TunnelSnapshot): boolean {
  return (
    a.animation === b.animation &&
    a.facing === b.facing &&
    a.frameIndex === b.frameIndex &&
    a.advance === b.advance &&
    a.faceSwingProgress === b.faceSwingProgress &&
    a.swingFraction === b.swingFraction &&
    a.digRate === b.digRate &&
    a.haulPhase === b.haulPhase &&
    a.haulProgress === b.haulProgress &&
    a.faceSlide === b.faceSlide &&
    a.crewSize === b.crewSize &&
    a.heapLoads === b.heapLoads &&
    fallingOreEqual(a.fallingOre, b.fallingOre) &&
    haulerFieldsEqual(a.hauler, b.hauler)
  );
}

function faceLeft(faceSlide: number): number {
  return FACE_X + (1 - faceSlide) * (PANE_WIDTH - FACE_X);
}

function dwarfLeft(snap: TunnelSnapshot): number {
  if (snap.hauler !== undefined) {
    return MINING_MARK_X;
  }
  if (snap.faceSlide < 1) {
    return MINING_MARK_X;
  }
  const span = MINING_MARK_X - CART_MARK_X;
  const t = snap.haulProgress;
  if (t <= 0.5) {
    return Math.round(MINING_MARK_X - (t / 0.5) * span);
  }
  return Math.round(CART_MARK_X + ((t - 0.5) / 0.5) * span);
}

function isPickupReturnLeg(snap: TunnelSnapshot): boolean {
  return (
    snap.crewSize === 2 &&
    snap.hauler?.phase === "pickup" &&
    snap.hauler.pickupProgress > 0.5
  );
}

function visibleHeapLoads(snap: TunnelSnapshot): number {
  if (isPickupReturnLeg(snap)) {
    return snap.heapLoads - 1;
  }
  return snap.heapLoads;
}

function haulerLeft(snap: TunnelSnapshot): number {
  const hauler = snap.hauler;
  if (!hauler) {
    throw new Error("haulerLeft requires a Hauler snapshot");
  }
  if (hauler.phase === "pickup") {
    if (snap.heapLoads === 0) {
      return HAULER_MARK_X;
    }
    const p = hauler.pickupProgress;
    const target = haulerPickupTargetX(snap.heapLoads);
    if (p <= 0.5) {
      return Math.round(HAULER_MARK_X + (p / 0.5) * (target - HAULER_MARK_X));
    }
    return Math.round(
      target - ((p - 0.5) / 0.5) * (target - HAULER_MARK_X),
    );
  }
  const span = HAULER_MARK_X - CART_MARK_X;
  const t = hauler.haulProgress;
  if (t <= 0.5) {
    return Math.round(HAULER_MARK_X - (t / 0.5) * span);
  }
  return Math.round(CART_MARK_X + ((t - 0.5) / 0.5) * span);
}

export function mountMiningTunnel(host: HTMLElement): MiningTunnelView {
  const layout = dwarfLayout(DWARF_PACK);
  const dwarfW = layout.frameW * DWARF_SCALE;
  const dwarfH = layout.frameH * DWARF_SCALE;

  const tunnel = document.createElement("div");
  tunnel.className = "pane-tunnel";
  tunnel.style.width = `${PANE_WIDTH}px`;
  tunnel.style.height = `${PANE_HEIGHT}px`;

  const world = document.createElement("div");
  world.className = "pane-tunnel-world";

  const columns: HTMLElement[] = [];
  for (let i = 0; i < VISIBLE_COLUMNS; i += 1) {
    const col = document.createElement("div");
    col.className = "pane-block";
    col.style.left = `${i * BLOCK_SIZE}px`;
    if (i === FACE_COLUMN_INDEX) {
      col.dataset["face"] = "";
    }
    columns.push(col);
    world.append(col);
  }

  const floor = document.createElement("div");
  floor.className = "pane-tunnel-floor";
  floor.style.background = FLOOR;
  floor.style.left = "0px";
  floor.style.width = `${PANE_WIDTH}px`;
  world.append(floor);

  const cart = document.createElement("div");
  cart.className = "pane-cart";
  cart.style.left = `${CART_X}px`;
  cart.style.width = `${CART_WIDTH}px`;
  cart.style.height = `${CART_HEIGHT}px`;
  cart.style.background = CART_FILL;

  const heap = document.createElement("div");
  heap.className = "pane-heap";
  const oreElements: HTMLElement[] = [];

  const dwarf = document.createElement("img");
  dwarf.className = "pane-dwarf";
  dwarf.alt = "Dwarf";
  dwarf.dataset["dwarf"] = "";
  dwarf.width = dwarfW;
  dwarf.height = dwarfH;
  dwarf.draggable = false;
  dwarf.style.width = `${dwarfW}px`;
  dwarf.style.height = `${dwarfH}px`;
  dwarf.style.imageRendering = "pixelated";

  const hauler = document.createElement("img");
  hauler.className = "pane-dwarf pane-hauler";
  hauler.alt = "Hauler";
  hauler.dataset["hauler"] = "";
  hauler.width = dwarfW;
  hauler.height = dwarfH;
  hauler.draggable = false;
  hauler.style.width = `${dwarfW}px`;
  hauler.style.height = `${dwarfH}px`;
  hauler.style.imageRendering = "pixelated";

  const dwarfBottom = 10;
  dwarf.style.bottom = `${dwarfBottom}px`;
  hauler.style.bottom = `${dwarfBottom}px`;

  const urlCache = new Map<string, string[]>();
  function urlsFor(
    pack: ExternalSpritePack,
    animation: string,
    facing: string,
    resolve: (
      pack: ExternalSpritePack,
      animation: string,
      facing: string,
    ) => string[],
    packId: string,
  ): string[] {
    const key = `${packId}:${animation}:${facing}`;
    let urls = urlCache.get(key);
    if (!urls) {
      urls = resolve(pack, animation, facing);
      urlCache.set(key, urls);
    }
    return urls;
  }

  tunnel.append(world, cart, dwarf);
  host.replaceChildren(tunnel);

  let heapMounted = false;

  function mountHeap(): void {
    if (!heapMounted) {
      tunnel.insertBefore(heap, cart);
      heapMounted = true;
    }
  }

  function unmountHeap(): void {
    if (heapMounted) {
      while (oreElements.length > 0) {
        const ore = oreElements.pop()!;
        ore.remove();
      }
      heap.remove();
      heapMounted = false;
    }
  }

  function positionHeapOre(snap: TunnelSnapshot): void {
    const fallingBySlot = new Map(
      snap.fallingOre.map((entry) => [entry.slot, entry.progress]),
    );
    const loads = visibleHeapLoads(snap);
    for (let slot = 0; slot < loads; slot += 1) {
      const ore = oreElements[slot];
      if (!ore) {
        continue;
      }
      const progress = fallingBySlot.get(slot);
      const { left, bottom } =
        progress !== undefined
          ? fallingOrePosition(slot, progress)
          : heapSlot(slot);
      ore.style.left = `${left}px`;
      ore.style.bottom = `${bottom}px`;
    }
  }

  function reconcileHeap(loads: number, crewSize: number): void {
    if (crewSize !== 2) {
      unmountHeap();
      return;
    }
    mountHeap();
    const targetCount = loads;
    while (oreElements.length > targetCount) {
      const ore = oreElements.pop()!;
      ore.remove();
    }
    while (oreElements.length < targetCount) {
      const slot = oreElements.length;
      const ore = document.createElement("div");
      ore.className = "pane-ore";
      ore.dataset["ore"] = "";
      ore.dataset["oreSlot"] = String(slot);
      const { left, bottom } = heapSlot(slot);
      ore.style.left = `${left}px`;
      ore.style.bottom = `${bottom}px`;
      ore.style.width = `${ORE_SIZE}px`;
      ore.style.height = `${ORE_SIZE}px`;
      ore.style.background = FACE;
      oreElements.push(ore);
      heap.append(ore);
    }
  }

  let haulerMounted = false;
  let carriedOre: HTMLElement | null = null;
  let lastSnap: TunnelSnapshot | null = null;

  function reconcileCarriedOre(snap: TunnelSnapshot): void {
    const show = isPickupReturnLeg(snap) && snap.heapLoads >= 1;

    if (!show) {
      if (carriedOre) {
        carriedOre.remove();
        carriedOre = null;
      }
      return;
    }

    if (!carriedOre) {
      carriedOre = document.createElement("div");
      carriedOre.className = "pane-ore";
      carriedOre.dataset["oreCarried"] = "";
      carriedOre.style.width = `${ORE_SIZE}px`;
      carriedOre.style.height = `${ORE_SIZE}px`;
      carriedOre.style.background = FACE;
      tunnel.append(carriedOre);
    }

    carriedOre.style.left = `${haulerLeft(snap)}px`;
    carriedOre.style.bottom = `${dwarfBottom}px`;
  }

  function mountHauler(): void {
    if (!haulerMounted) {
      tunnel.append(hauler);
      haulerMounted = true;
    }
  }

  function unmountHauler(): void {
    if (haulerMounted) {
      hauler.remove();
      haulerMounted = false;
    }
  }

  function render(snap: TunnelSnapshot): void {
    if (lastSnap !== null && snapEquals(lastSnap, snap)) {
      return;
    }
    lastSnap = {
      ...snap,
      fallingOre: [...snap.fallingOre],
      ...(snap.hauler ? { hauler: { ...snap.hauler } } : {}),
    };

    world.style.transform = "";

    const faceColumnLeft = faceLeft(snap.faceSlide);

    for (let i = 0; i < VISIBLE_COLUMNS; i += 1) {
      const gridLeft = i * BLOCK_SIZE;
      const col = columns[i]!;
      col.style.width = `${BLOCK_SIZE}px`;
      col.style.height = `${PANE_HEIGHT}px`;

      const existingCrack = col.querySelector(".pane-face-crack");
      if (existingCrack) {
        existingCrack.remove();
      }

      if (i === FACE_COLUMN_INDEX) {
        col.style.left = `${faceColumnLeft}px`;
        const hardness = hardnessFor(snap.advance);
        const crackProgress =
          (snap.faceSwingProgress + snap.swingFraction) / hardness;
        if (crackProgress > 0) {
          const crack = document.createElement("div");
          crack.className = "pane-face-crack";
          crack.style.opacity = String(0.25 + crackProgress * 0.75);
          crack.style.background = CRACK;
          col.style.background = FACE_DEEP;
          col.append(crack);
        } else {
          col.style.background = FACE;
        }
      } else {
        col.style.left = `${gridLeft}px`;
        if (gridLeft < FACE_X) {
          col.style.background = HOLLOW;
        } else {
          col.style.background = SOLID;
        }
      }
    }

    dwarf.style.left = `${dwarfLeft(snap)}px`;

    const dwarfUrls = urlsFor(
      DWARF_PACK,
      snap.animation,
      snap.facing,
      dwarfFrameUrlsFor,
      "dwarf",
    );
    const dwarfFrame = dwarfUrls[snap.frameIndex] ?? dwarfUrls[0];
    if (!dwarfFrame) {
      throw new Error(`Missing dwarf frame for ${snap.animation}/${snap.facing}`);
    }
    dwarf.src = dwarfFrame;
    dwarf.dataset["anim"] = snap.animation;
    dwarf.dataset["frame"] = String(snap.frameIndex);

    if (snap.hauler) {
      mountHauler();
      hauler.style.left = `${haulerLeft(snap)}px`;
      const haulerUrls = urlsFor(
        HAULER_PACK,
        snap.hauler.animation,
        snap.hauler.facing,
        haulerFrameUrlsFor,
        "hauler",
      );
      const haulerFrame = haulerUrls[snap.hauler.frameIndex] ?? haulerUrls[0];
      if (!haulerFrame) {
        throw new Error(
          `Missing hauler frame for ${snap.hauler.animation}/${snap.hauler.facing}`,
        );
      }
      hauler.src = haulerFrame;
      hauler.dataset["anim"] = snap.hauler.animation;
      hauler.dataset["frame"] = String(snap.hauler.frameIndex);
    } else {
      unmountHauler();
    }

    reconcileHeap(visibleHeapLoads(snap), snap.crewSize);
    positionHeapOre(snap);
    reconcileCarriedOre(snap);
  }

  return {
    root: tunnel,
    render,
    destroy() {
      host.replaceChildren();
    },
  };
}

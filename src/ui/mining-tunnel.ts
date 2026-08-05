/** Pane mining Tunnel: fixed-camera arena, Cart, Dwarf Haul travel, Face slide-in.

Composition from [Prototype the mining scene at 480x112](#318): full-band Tunnel,
Colony corner chip, cyan Face, no Dig Rate / Ore / Ingots on the Pane.
*/
import type { HeapOreSnapshot, TunnelSnapshot } from "./mine-presenter";
import { hardnessFor } from "../core/mining-engine";
import { dwarfLayout, type ExternalSpritePack } from "../data/external-sprite-pack";
import { tunnelArtContentBottomGap, tunnelArtPath } from "../data/tunnel-art-pack";
import { DWARF_PACK, dwarfFrameUrlsFor } from "./dwarf-frames";
import { HAULER_PACK, haulerFrameUrlsFor } from "./hauler-frames";
import { fallingOrePosition } from "./heap-pile";
import {
  HEAP_ORE_VARIANT_COUNT,
  heapOreArtKey,
} from "./heap-ore-variants";
import {
  BLOCK_SIZE,
  CART_HEIGHT,
  CART_WIDTH,
  CART_X,
  DWARF_SCALE,
  FACE_X,
  FLOOR_Y,
  HAULER_HAND_DX,
  HAULER_HAND_DY,
  ORE_SIZE,
  PANE_HEIGHT,
  PANE_WIDTH,
} from "./pane-layout";
import { TUNNEL_ART_PACK, tunnelArtUrl } from "./tunnel-art";

function adjustedHeapOreBottom(slotBottom: number, artKey: string): number {
  return (
    slotBottom -
    tunnelArtContentBottomGap(TUNNEL_ART_PACK, artKey, ORE_SIZE)
  );
}

function paintOreArt(ore: HTMLElement, artKey: string): void {
  const tilePath = tunnelArtPath(TUNNEL_ART_PACK, artKey);
  ore.style.backgroundImage = `url("${tunnelArtUrl(tilePath)}")`;
  ore.style.backgroundSize = `${ORE_SIZE}px ${ORE_SIZE}px`;
  ore.style.imageRendering = "pixelated";
  ore.dataset["oreVariant"] = artKey;
}

function paintHeapOre(
  ore: HTMLElement,
  artKey: string,
  slotBottom: number,
): void {
  paintOreArt(ore, artKey);
  ore.style.bottom = `${adjustedHeapOreBottom(slotBottom, artKey)}px`;
}

export interface MiningTunnelView {
  root: HTMLElement;
  render(snap: TunnelSnapshot): void;
  destroy(): void;
}

const CART_FILL = "#5C4A58";

export type FaceDamageState = "intact" | "chipped" | "cracked" | "crumbling";

export function faceDamageState(progress: number): FaceDamageState {
  if (progress < 0 || progress > 1) {
    throw new Error(`Face damage progress out of range: ${progress}`);
  }
  if (progress < 0.25) {
    return "intact";
  }
  if (progress < 0.5) {
    return "chipped";
  }
  if (progress < 0.75) {
    return "cracked";
  }
  return "crumbling";
}

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
    a.pickupProgress === b.pickupProgress &&
    a.left === b.left
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
    if (
      a[i]!.slot !== b[i]!.slot ||
      a[i]!.progress !== b[i]!.progress
    ) {
      return false;
    }
  }
  return true;
}

function heapOreEqual(
  a: readonly HeapOreSnapshot[],
  b: readonly HeapOreSnapshot[],
): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i += 1) {
    const ao = a[i]!;
    const bo = b[i]!;
    if (
      ao.id !== bo.id ||
      ao.left !== bo.left ||
      ao.bottom !== bo.bottom ||
      ao.variantIndex !== bo.variantIndex
    ) {
      return false;
    }
  }
  return true;
}

function carriedIndexesEqual(
  a: TunnelSnapshot["carriedVariantIndexes"],
  b: TunnelSnapshot["carriedVariantIndexes"],
): boolean {
  const left = a ?? [];
  const right = b ?? [];
  if (left.length !== right.length) {
    return false;
  }
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) {
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
    a.pickDamage === b.pickDamage &&
    a.digRate === b.digRate &&
    a.haulPhase === b.haulPhase &&
    a.haulProgress === b.haulProgress &&
    a.faceSlide === b.faceSlide &&
    a.crewSize === b.crewSize &&
    a.minerLeft === b.minerLeft &&
    a.haulRemainingMs === b.haulRemainingMs &&
    carriedIndexesEqual(a.carriedVariantIndexes, b.carriedVariantIndexes) &&
    heapOreEqual(a.heapOre, b.heapOre) &&
    fallingOreEqual(a.fallingOre, b.fallingOre) &&
    haulerFieldsEqual(a.hauler, b.hauler)
  );
}

function faceLeft(faceSlide: number): number {
  return FACE_X + (1 - faceSlide) * (PANE_WIDTH - FACE_X);
}

function dwarfLeft(snap: TunnelSnapshot): number {
  return snap.minerLeft;
}

function haulerLeft(snap: TunnelSnapshot): number {
  const hauler = snap.hauler;
  if (!hauler) {
    throw new Error("haulerLeft requires a Hauler snapshot");
  }
  return hauler.left;
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
  const backgroundPath = tunnelArtPath(
    TUNNEL_ART_PACK,
    "background/tunnel-interior",
  );
  world.style.backgroundImage = `url("${tunnelArtUrl(backgroundPath)}")`;
  world.style.backgroundSize = `${PANE_WIDTH}px ${PANE_HEIGHT}px`;
  world.style.imageRendering = "pixelated";

  const faceColumn = document.createElement("div");
  faceColumn.className = "pane-block";
  faceColumn.dataset["face"] = "";
  faceColumn.style.left = `${FACE_X}px`;
  world.append(faceColumn);

  const cart = document.createElement("div");
  cart.className = "pane-cart";
  cart.style.left = `${CART_X}px`;
  cart.style.width = `${CART_WIDTH}px`;
  cart.style.height = `${CART_HEIGHT}px`;
  cart.style.bottom = `${FLOOR_Y}px`;
  cart.style.background = CART_FILL;

  const heap = document.createElement("div");
  heap.className = "pane-heap";
  const oreById = new Map<number, HTMLElement>();
  const bagFallElements: HTMLElement[] = [];

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

  dwarf.style.bottom = `${FLOOR_Y}px`;
  hauler.style.bottom = `${FLOOR_Y}px`;

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
      for (const ore of oreById.values()) {
        ore.remove();
      }
      oreById.clear();
      heap.remove();
      heapMounted = false;
    }
  }

  function reconcileBagFalls(snap: TunnelSnapshot): void {
    const bagFalls = snap.fallingOre;
    while (bagFallElements.length > bagFalls.length) {
      const ore = bagFallElements.pop()!;
      ore.remove();
    }
    while (bagFallElements.length < bagFalls.length) {
      const ore = document.createElement("div");
      ore.className = "pane-ore";
      ore.dataset["ore"] = "";
      ore.style.width = `${ORE_SIZE}px`;
      ore.style.height = `${ORE_SIZE}px`;
      bagFallElements.push(ore);
      tunnel.append(ore);
    }
    for (let i = 0; i < bagFalls.length; i += 1) {
      const entry = bagFalls[i]!;
      const ore = bagFallElements[i]!;
      const artKey = heapOreArtKey(entry.slot % HEAP_ORE_VARIANT_COUNT);
      const { left, bottom } = fallingOrePosition(entry.slot, entry.progress);
      ore.style.left = `${left}px`;
      paintHeapOre(ore, artKey, bottom);
    }
  }

  function reconcileHeap(snap: TunnelSnapshot): void {
    if (snap.crewSize !== 2) {
      unmountHeap();
      return;
    }
    mountHeap();
    const idsInSnap = new Set(snap.heapOre.map((entry) => entry.id));
    for (const [id, ore] of oreById) {
      if (!idsInSnap.has(id)) {
        ore.remove();
        oreById.delete(id);
      }
    }
    for (const entry of snap.heapOre) {
      let ore = oreById.get(entry.id);
      if (!ore) {
        ore = document.createElement("div");
        ore.className = "pane-ore";
        ore.dataset["ore"] = "";
        ore.dataset["oreId"] = String(entry.id);
        ore.style.width = `${ORE_SIZE}px`;
        ore.style.height = `${ORE_SIZE}px`;
        oreById.set(entry.id, ore);
        heap.append(ore);
      }
      const artKey = heapOreArtKey(entry.variantIndex);
      ore.style.left = `${entry.left}px`;
      ore.style.bottom = `${entry.bottom}px`;
      paintOreArt(ore, artKey);
    }
  }

  let haulerMounted = false;
  const carriedOreBySlot: HTMLElement[] = [];
  let lastSnap: TunnelSnapshot | null = null;

  function reconcileCarriedOre(snap: TunnelSnapshot): void {
    const indexes = snap.carriedVariantIndexes ?? [];
    while (carriedOreBySlot.length > indexes.length) {
      carriedOreBySlot.pop()!.remove();
    }
    while (carriedOreBySlot.length < indexes.length) {
      const ore = document.createElement("div");
      ore.className = "pane-ore pane-ore-carried";
      ore.dataset["oreCarried"] = "";
      ore.style.width = `${ORE_SIZE}px`;
      ore.style.height = `${ORE_SIZE}px`;
      tunnel.append(ore);
      carriedOreBySlot.push(ore);
    }

    if (indexes.length === 0) {
      return;
    }

    const left = haulerLeft(snap);
    const facing = snap.hauler?.facing ?? "east";
    const handDx =
      facing === "west"
        ? dwarfW - ORE_SIZE - HAULER_HAND_DX
        : HAULER_HAND_DX;

    for (let i = 0; i < indexes.length; i += 1) {
      const ore = carriedOreBySlot[i]!;
      const artKey = heapOreArtKey(indexes[i]!);
      paintHeapOre(ore, artKey, FLOOR_Y + HAULER_HAND_DY);
      ore.style.left = `${left + handDx}px`;
    }
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
      heapOre: [...snap.heapOre],
      fallingOre: [...snap.fallingOre],
      ...(snap.hauler ? { hauler: { ...snap.hauler } } : {}),
    };

    world.style.transform = "";

    const faceColumnLeft = faceLeft(snap.faceSlide);

    faceColumn.style.width = `${BLOCK_SIZE}px`;
    faceColumn.style.height = `${PANE_HEIGHT}px`;
    faceColumn.style.left = `${faceColumnLeft}px`;

    const hardness = hardnessFor(snap.advance);
    const faceProgress =
      (snap.faceSwingProgress + snap.swingFraction) * snap.pickDamage / hardness;
    const damageState = faceDamageState(faceProgress);
    const faceTilePath = tunnelArtPath(
      TUNNEL_ART_PACK,
      `tiles/face/${damageState}`,
    );
    faceColumn.style.backgroundImage = `url("${tunnelArtUrl(faceTilePath)}")`;
    faceColumn.style.backgroundRepeat = "repeat-y";
    faceColumn.style.backgroundSize = "48px 48px";
    faceColumn.style.imageRendering = "pixelated";

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

    reconcileHeap(snap);
    reconcileBagFalls(snap);
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

/** Pane mining Tunnel: fixed-camera arena, Cart, Dwarf Haul travel, Face slide-in.

Composition from [Prototype the mining scene at 480x112](#318): full-band Tunnel,
Colony corner chip, cyan Face, no Dig Rate / Ore / Ingots on the Pane.
*/
import type { TunnelSnapshot } from "./mine-presenter";
import { hardnessFor } from "../core/mining-engine";
import { dwarfLayout } from "../data/external-sprite-pack";
import { DWARF_PACK, dwarfFrameUrlsFor } from "./dwarf-frames";
import {
  BLOCK_SIZE,
  CART_HEIGHT,
  CART_MARK_X,
  CART_WIDTH,
  CART_X,
  DWARF_SCALE,
  FACE_X,
  MINING_MARK_X,
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
    a.faceSlide === b.faceSlide
  );
}

function faceLeft(faceSlide: number): number {
  return FACE_X + (1 - faceSlide) * (PANE_WIDTH - FACE_X);
}

function dwarfLeft(snap: TunnelSnapshot): number {
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

  const dwarfBottom = 10;
  dwarf.style.bottom = `${dwarfBottom}px`;

  const urlCache = new Map<string, string[]>();
  function urlsFor(animation: string, facing: string): string[] {
    const key = `${animation}:${facing}`;
    let urls = urlCache.get(key);
    if (!urls) {
      urls = dwarfFrameUrlsFor(DWARF_PACK, animation, facing);
      urlCache.set(key, urls);
    }
    return urls;
  }

  tunnel.append(world, cart, dwarf);
  host.replaceChildren(tunnel);

  let lastSnap: TunnelSnapshot | null = null;

  function render(snap: TunnelSnapshot): void {
    if (lastSnap !== null && snapEquals(lastSnap, snap)) {
      return;
    }
    lastSnap = { ...snap };

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

    const urls = urlsFor(snap.animation, snap.facing);
    const frame = urls[snap.frameIndex] ?? urls[0];
    if (!frame) {
      throw new Error(`Missing dwarf frame for ${snap.animation}/${snap.facing}`);
    }
    dwarf.src = frame;
    dwarf.dataset["anim"] = snap.animation;
    dwarf.dataset["frame"] = String(snap.frameIndex);
  }

  return {
    root: tunnel,
    render,
    destroy() {
      host.replaceChildren();
    },
  };
}

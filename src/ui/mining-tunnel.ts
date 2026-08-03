/** Pane mining Tunnel: planted Dwarf at 3×, scrolling Face, placeholder fills.

Composition from [Prototype the mining scene at 480x112](#318): full-band Tunnel,
Colony corner chip, cyan Face, no Dig Rate / Ore / Ingots on the Pane.
*/
import type { DemoMineSnapshot } from "../core/demo-mine-loop";
import { HARDNESS } from "../core/mining-engine";
import { dwarfLayout } from "../data/external-sprite-pack";
import { DWARF_PACK, dwarfFrameUrlsFor } from "./dwarf-frames";
import {
  BLOCK_SIZE,
  DWARF_SCALE,
  PANE_HEIGHT,
  PANE_WIDTH,
} from "./pane-layout";

export interface MiningTunnelView {
  root: HTMLElement;
  render(snap: DemoMineSnapshot): void;
  destroy(): void;
}

const SOLID = "#4A3B48";
const HOLLOW = "#1D1720";
const FACE = "#27A6A3";
const FACE_DEEP = "#176873";
const CRACK = "#72E2D2";
const FLOOR = "#3B2F3A";

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

  // Planted Dwarf: feet near floor, left of centre-east so Face reads ahead.
  const dwarfScreenX = Math.floor(PANE_WIDTH * 0.38) - dwarfW;
  const dwarfBottom = 10;
  dwarf.style.left = `${dwarfScreenX}px`;
  dwarf.style.bottom = `${dwarfBottom}px`;

  tunnel.append(world, dwarf);
  host.replaceChildren(tunnel);

  function render(snap: DemoMineSnapshot): void {
    const faceScreenX = PANE_WIDTH - BLOCK_SIZE - 16;
    const scrollX = Math.max(0, snap.advance * BLOCK_SIZE - (faceScreenX - BLOCK_SIZE));
    world.style.transform = `translateX(${-scrollX}px)`;

    const total = snap.advance + 14;
    world.replaceChildren();
    for (let i = 0; i < total; i += 1) {
      const col = document.createElement("div");
      col.className = "pane-block";
      col.style.left = `${i * BLOCK_SIZE}px`;
      col.style.width = `${BLOCK_SIZE}px`;
      col.style.height = `${PANE_HEIGHT}px`;
      if (i < snap.advance) {
        col.style.background = HOLLOW;
      } else if (i === snap.advance) {
        col.style.background = FACE;
        const crackProgress =
          (snap.faceSwingProgress + snap.swingFraction) / HARDNESS;
        if (crackProgress > 0) {
          const crack = document.createElement("div");
          crack.className = "pane-face-crack";
          crack.style.opacity = String(0.25 + crackProgress * 0.75);
          crack.style.background = CRACK;
          col.style.background = FACE_DEEP;
          col.append(crack);
        }
      } else {
        col.style.background = SOLID;
      }
      world.append(col);
    }

    const floor = document.createElement("div");
    floor.className = "pane-tunnel-floor";
    floor.style.width = `${total * BLOCK_SIZE}px`;
    floor.style.background = FLOOR;
    world.append(floor);

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

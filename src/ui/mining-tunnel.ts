/** Pane mining Tunnel: planted Dwarf at 3×, scrolling Face, placeholder fills.

Composition from [Prototype the mining scene at 480x112](#318): full-band Tunnel,
Colony corner chip, cyan Face, no Dig Rate / Ore / Ingots on the Pane.
*/
import type { TunnelSnapshot } from "./mine-presenter";
import { hardnessFor } from "../core/mining-engine";
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
  render(snap: TunnelSnapshot): void;
  destroy(): void;
}

const SOLID = "#4A3B48";
const HOLLOW = "#1D1720";
const FACE = "#27A6A3";
const FACE_DEEP = "#176873";
const CRACK = "#72E2D2";
const FLOOR = "#3B2F3A";

const VISIBLE_COLUMNS = Math.ceil(PANE_WIDTH / BLOCK_SIZE) + 2;

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
    a.haulProgress === b.haulProgress
  );
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
    columns.push(col);
    world.append(col);
  }

  const floor = document.createElement("div");
  floor.className = "pane-tunnel-floor";
  floor.style.background = FLOOR;
  world.append(floor);

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

  let lastSnap: TunnelSnapshot | null = null;

  function render(snap: TunnelSnapshot): void {
    if (lastSnap !== null && snapEquals(lastSnap, snap)) {
      return;
    }
    lastSnap = { ...snap };

    const faceScreenX = PANE_WIDTH - BLOCK_SIZE - 16;
    const scrollX = Math.max(
      0,
      snap.advance * BLOCK_SIZE - (faceScreenX - BLOCK_SIZE),
    );
    world.style.transform = `translateX(${-scrollX}px)`;

    const startIndex = Math.floor(scrollX / BLOCK_SIZE) - 1;

    for (let j = 0; j < VISIBLE_COLUMNS; j += 1) {
      const worldIndex = startIndex + j;
      const col = columns[j]!;
      col.style.left = `${worldIndex * BLOCK_SIZE}px`;
      col.style.width = `${BLOCK_SIZE}px`;
      col.style.height = `${PANE_HEIGHT}px`;

      const existingCrack = col.querySelector(".pane-face-crack");
      if (existingCrack) {
        existingCrack.remove();
      }

      if (worldIndex < snap.advance) {
        col.style.background = HOLLOW;
      } else if (worldIndex === snap.advance) {
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
        col.style.background = SOLID;
      }
    }

    floor.style.left = `${startIndex * BLOCK_SIZE}px`;
    floor.style.width = `${VISIBLE_COLUMNS * BLOCK_SIZE}px`;

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

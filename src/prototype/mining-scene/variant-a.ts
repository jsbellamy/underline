import dwarfIdleEastUrl from "../../../assets/characters/dwarf/idle/east/frame_000.png";
import dwarfSwingEastUrl from "../../../assets/characters/dwarf/swing/east/frame_004.png";
import type { SceneSnapshot } from "./moments";

export const VARIANT_A_NAME = "Chrome strip + fixed Dwarf";

const BLOCK = 32;
const SCALE = 4;
const DWARF_W = 26 * SCALE;
const DWARF_H = 18 * SCALE;

/** Dig Rate chrome kept; Ore + Ingots join it. Dwarf planted; world scrolls under him. */
export function mountVariantA(host: HTMLElement, snap: SceneSnapshot): void {
  const pane = document.createElement("div");
  pane.className = "msp-pane msp-a";

  const chrome = document.createElement("div");
  chrome.className = "msp-a-chrome";
  chrome.innerHTML = `
    <span class="msp-stat"><b>Dig Rate</b> ${formatRate(snap.digRate)}</span>
    <span class="msp-stat"><b>Ore</b> ${snap.ore}</span>
    <span class="msp-stat"><b>Ingots</b> ${snap.ingots}</span>
    <button type="button" class="msp-colony" tabindex="-1">Colony</button>
  `;

  const band = document.createElement("div");
  band.className = "msp-a-band";

  const world = document.createElement("div");
  world.className = "msp-a-world";
  // Face sits just east of the planted Dwarf; scroll so that stays true as Advance grows.
  const dwarfScreenX = 120;
  const faceWorldX = snap.advance * BLOCK;
  const scrollX = faceWorldX - (dwarfScreenX + DWARF_W - 8);
  world.style.transform = `translateX(${-scrollX}px)`;

  const tunnelLength = Math.max(snap.advance, 1);
  const ahead = 10;
  for (let i = 0; i < tunnelLength + ahead; i += 1) {
    const block = document.createElement("div");
    block.className = "msp-a-block";
    block.style.left = `${i * BLOCK}px`;
    if (i < snap.advance) {
      block.classList.add("msp-excavated");
    } else if (i === snap.advance) {
      block.classList.add("msp-face");
      if (snap.swingProgress > 0) {
        const crack = document.createElement("div");
        crack.className = "msp-crack";
        crack.style.height = `${Math.round(snap.swingProgress * 100)}%`;
        block.append(crack);
      }
    } else {
      block.classList.add("msp-rock");
    }
    world.append(block);
  }

  const floor = document.createElement("div");
  floor.className = "msp-a-floor";
  floor.style.width = `${(tunnelLength + ahead) * BLOCK}px`;
  world.append(floor);

  const ceiling = document.createElement("div");
  ceiling.className = "msp-a-ceiling";
  ceiling.style.width = `${(tunnelLength + ahead) * BLOCK}px`;
  world.append(ceiling);

  band.append(world);

  const dwarf = document.createElement("img");
  dwarf.className = "msp-dwarf";
  dwarf.alt = "Dwarf";
  dwarf.src = snap.anim === "swing" ? dwarfSwingEastUrl : dwarfIdleEastUrl;
  dwarf.style.width = `${DWARF_W}px`;
  dwarf.style.height = `${DWARF_H}px`;
  dwarf.style.left = `${dwarfScreenX}px`;
  dwarf.style.bottom = "6px";
  band.append(dwarf);

  if (snap.ore >= 40) {
    const pile = document.createElement("div");
    pile.className = "msp-a-ore-pile";
    pile.title = "Ore backlog (Smelter behind)";
    pile.style.left = `${dwarfScreenX - 40}px`;
    band.append(pile);
  }

  pane.append(chrome, band);
  host.replaceChildren(pane);
}

function formatRate(rate: number): string {
  return Number.isInteger(rate) ? `${rate}/s` : `${rate.toFixed(1)}/s`;
}

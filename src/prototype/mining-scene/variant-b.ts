import dwarfIdleEastUrl from "../../../assets/characters/dwarf/idle/east/frame_000.png";
import dwarfSwingEastUrl from "../../../assets/characters/dwarf/swing/east/frame_004.png";
import type { SceneSnapshot } from "./moments";

export const VARIANT_B_NAME = "Full-bleed HUD overlay";

const BLOCK = 32;
const SCALE = 3;
const DWARF_W = 26 * SCALE;
const DWARF_H = 18 * SCALE;
const PANE_W = 480;
const PANE_H = 112;

/** No chrome band — whole Pane is Tunnel. Numbers float on the scene. Face pinned east. */
export function mountVariantB(host: HTMLElement, snap: SceneSnapshot): void {
  const pane = document.createElement("div");
  pane.className = "msp-pane msp-b";
  pane.style.width = `${PANE_W}px`;
  pane.style.height = `${PANE_H}px`;

  const faceScreenX = PANE_W - BLOCK - 16;
  const scrollX = snap.advance * BLOCK - (faceScreenX - BLOCK);
  const world = document.createElement("div");
  world.className = "msp-b-world";
  world.style.transform = `translateX(${-Math.max(0, scrollX)}px)`;

  const total = snap.advance + 12;
  for (let i = 0; i < total; i += 1) {
    const col = document.createElement("div");
    col.className = "msp-b-col";
    col.style.left = `${i * BLOCK}px`;
    if (i < snap.advance) {
      col.classList.add("msp-b-hollow");
    } else if (i === snap.advance) {
      col.classList.add("msp-b-face");
      const vein = document.createElement("div");
      vein.className = "msp-b-vein";
      col.append(vein);
      if (snap.swingProgress > 0) {
        const chip = document.createElement("div");
        chip.className = "msp-b-chip";
        chip.style.opacity = String(0.35 + snap.swingProgress * 0.65);
        col.append(chip);
      }
    } else {
      col.classList.add("msp-b-solid");
    }
    world.append(col);
  }

  const floorStripe = document.createElement("div");
  floorStripe.className = "msp-b-floor";
  floorStripe.style.width = `${total * BLOCK}px`;
  world.append(floorStripe);

  pane.append(world);

  const dwarfWorldX = snap.advance * BLOCK - 8;
  const dwarf = document.createElement("img");
  dwarf.className = "msp-dwarf";
  dwarf.alt = "Dwarf";
  dwarf.src = snap.anim === "swing" ? dwarfSwingEastUrl : dwarfIdleEastUrl;
  dwarf.style.width = `${DWARF_W}px`;
  dwarf.style.height = `${DWARF_H}px`;
  dwarf.style.left = `${dwarfWorldX - Math.max(0, scrollX) - DWARF_W}px`;
  dwarf.style.bottom = "10px";
  pane.append(dwarf);

  const hudTop = document.createElement("div");
  hudTop.className = "msp-b-hud-top";
  hudTop.innerHTML = `<span class="msp-b-dig"><b>Dig Rate</b> ${formatRate(snap.digRate)}</span>`;
  pane.append(hudTop);

  const hudBottom = document.createElement("div");
  hudBottom.className = "msp-b-hud-bottom";
  hudBottom.innerHTML = `
    <span class="msp-b-pill ore"><b>Ore</b> ${snap.ore}</span>
    <span class="msp-b-pill ingot"><b>Ingots</b> ${snap.ingots}</span>
  `;
  pane.append(hudBottom);

  if (snap.ore >= 40) {
    const backlog = document.createElement("div");
    backlog.className = "msp-b-backlog";
    backlog.textContent = "Smelter backlog";
    pane.append(backlog);
    for (let n = 0; n < 5; n += 1) {
      const nugget = document.createElement("div");
      nugget.className = "msp-b-nugget";
      nugget.style.left = `${48 + n * 10}px`;
      nugget.style.bottom = `${14 + (n % 3) * 6}px`;
      pane.append(nugget);
    }
  }

  const colony = document.createElement("button");
  colony.type = "button";
  colony.className = "msp-b-colony";
  colony.tabIndex = -1;
  colony.textContent = "Colony";
  pane.append(colony);

  host.replaceChildren(pane);
}

function formatRate(rate: number): string {
  return Number.isInteger(rate) ? `${rate}/s` : `${rate.toFixed(1)}/s`;
}

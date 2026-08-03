import dwarfIdleEastUrl from "../../../assets/characters/dwarf/idle/east/frame_000.png";
import dwarfSwingEastUrl from "../../../assets/characters/dwarf/swing/east/frame_004.png";
import type { SceneSnapshot } from "./moments";

export const VARIANT_C_NAME = "Meter column + small Dwarf";

const BLOCK = 32;
const SCALE = 2;
const DWARF_W = 26 * SCALE;
const DWARF_H = 18 * SCALE;
const METER_W = 96;
const SCENE_W = 480 - METER_W;

/**
 * Left meters steal width; Dig Rate is the only chrome number in spirit (Ore/Ingots
 * live in the meter column, not over the Tunnel). Small Dwarf so architecture reads.
 * Side-scroller camera: Dwarf walks right until the Face approaches the east edge.
 */
export function mountVariantC(host: HTMLElement, snap: SceneSnapshot): void {
  const pane = document.createElement("div");
  pane.className = "msp-pane msp-c";

  const meters = document.createElement("aside");
  meters.className = "msp-c-meters";
  meters.innerHTML = `
    <div class="msp-c-dig">
      <div class="msp-c-label">Dig Rate</div>
      <div class="msp-c-value">${formatRate(snap.digRate)}</div>
    </div>
    <div class="msp-c-stack">
      <div><span>Ore</span><b>${snap.ore}</b></div>
      <div><span>Ingots</span><b>${snap.ingots}</b></div>
      <div><span>Advance</span><b>${snap.advance}</b></div>
    </div>
    <button type="button" class="msp-c-colony" tabindex="-1">Colony</button>
  `;

  const scene = document.createElement("div");
  scene.className = "msp-c-scene";

  // Side-scroller: keep Face near the right third once Advance is large enough;
  // at Advance 0 the Dwarf starts near the west with rock filling the view.
  const faceIdeal = Math.floor(SCENE_W * 0.72);
  const faceWorldX = snap.advance * BLOCK;
  const scrollX = Math.max(0, faceWorldX - faceIdeal);
  const dwarfWorldX = faceWorldX - 4;

  const world = document.createElement("div");
  world.className = "msp-c-world";
  world.style.transform = `translateX(${-scrollX}px)`;

  const total = snap.advance + 14;
  for (let i = 0; i < total; i += 1) {
    const block = document.createElement("div");
    block.className = "msp-c-block";
    block.style.left = `${i * BLOCK}px`;
    if (i < snap.advance) {
      block.classList.add("msp-c-broken");
    } else if (i === snap.advance) {
      block.classList.add("msp-c-face");
      const ticks = document.createElement("div");
      ticks.className = "msp-c-hardness";
      for (let h = 0; h < snap.hardness; h += 1) {
        const tick = document.createElement("span");
        if (h < Math.floor(snap.swingProgress * snap.hardness)) {
          tick.classList.add("done");
        }
        ticks.append(tick);
      }
      block.append(ticks);
    } else {
      block.classList.add("msp-c-ahead");
    }
    world.append(block);
  }

  const rib = document.createElement("div");
  rib.className = "msp-c-rib";
  rib.style.width = `${total * BLOCK}px`;
  world.append(rib);

  scene.append(world);

  const dwarf = document.createElement("img");
  dwarf.className = "msp-dwarf";
  dwarf.alt = "Dwarf";
  dwarf.src = snap.anim === "swing" ? dwarfSwingEastUrl : dwarfIdleEastUrl;
  dwarf.style.width = `${DWARF_W}px`;
  dwarf.style.height = `${DWARF_H}px`;
  dwarf.style.left = `${dwarfWorldX - scrollX - DWARF_W}px`;
  dwarf.style.bottom = "8px";
  scene.append(dwarf);

  if (snap.ore >= 40) {
    const note = document.createElement("div");
    note.className = "msp-c-backlog-note";
    note.textContent = "Ore waiting on Smelter";
    scene.append(note);
  }

  // First-open callout when empty
  if (snap.moment === "first-open") {
    const empty = document.createElement("div");
    empty.className = "msp-c-empty";
    empty.textContent = "Face ahead — start swinging";
    scene.append(empty);
  }

  pane.append(meters, scene);
  host.replaceChildren(pane);
}

function formatRate(rate: number): string {
  return Number.isInteger(rate) ? `${rate}/s` : `${rate.toFixed(1)}/s`;
}

/** Pane outer size and mining composition constants.

Composition (#318): no Dig Rate chrome — Tunnel uses the full 480×112;
Dig Rate / Ore / Ingots readouts are Dock-only. Dwarf draws at 3× integer scale.
*/

import { HAUL_ROUND_TRIP_MS } from "../core/mining-engine";

export const PANE_WIDTH = 480;
export const PANE_HEIGHT = 112;
/** Full-band Tunnel — equals Pane height (chrome removed). */
export const TUNNEL_HEIGHT = PANE_HEIGHT;
/** Integer nearest-neighbor scale for the external dwarf pack (#318). */
export const DWARF_SCALE = 3;
/** Placeholder Mineable Block width in Pane pixels. */
export const BLOCK_SIZE = 32;

/** External dwarf pack frame width in source pixels. */
export const DWARF_FRAME_W = 26;

/** Cart placeholder at the Pane's west edge. */
export const CART_X = 8;
export const CART_WIDTH = 40;
export const CART_HEIGHT = 24;

/** Face column mark — east of the Dwarf's mining stand. */
export const FACE_X = 336;

export const CART_MARK_X = CART_X + CART_WIDTH + 8;
const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
export const MINING_MARK_X = FACE_X - dwarfW;

/** The Hauler's stand while lifting Loads — immediately west of the Miner. */
export const HAULER_MARK_X = MINING_MARK_X - dwarfW;

/** Presentation Haul speed derived from the engine's one Haul duration. */
export const HAUL_SPEED_PX_PER_MS =
  (MINING_MARK_X - CART_MARK_X) / (HAUL_ROUND_TRIP_MS / 2);

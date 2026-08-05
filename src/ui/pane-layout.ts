/** Pane outer size and mining composition constants.

Composition (#318): no Dig Rate chrome — Tunnel uses the full 480×112;
Dig Rate / Ore / Ingots readouts are Dock-only. Dwarf draws at 3× integer scale.
*/

import { HAUL_TRAVEL_MS } from "../core/mining-engine";

export const PANE_WIDTH = 480;
export const PANE_HEIGHT = 112;
/** Full-band Tunnel — equals Pane height (chrome removed). */
export const TUNNEL_HEIGHT = PANE_HEIGHT;
/** Integer nearest-neighbor scale for the external dwarf pack (#318). */
export const DWARF_SCALE = 3;
/** Placeholder Mineable Block width in Pane pixels. */
export const BLOCK_SIZE = 48;

/** External dwarf pack frame width in source pixels. */
export const DWARF_FRAME_W = 26;

/** Cart placeholder east of the reserved west band (0…104). */
export const CART_X = 104;
export const CART_WIDTH = 40;
export const CART_HEIGHT = 24;

/** Face column mark — east of the Dwarf's mining stand. */
export const FACE_X = 432;

/** Native Ore object size in Pane pixels — object-set art is never scaled (#442). */
export const ORE_SIZE = 32;
/** Heap floor band — rests on the 8px floor. */
export const HEAP_BOTTOM = 8;
/** Shared Pane floor token — Dwarves, Cart, and settled Ore stand here. */
export const FLOOR_Y = HEAP_BOTTOM;
/** Vertical cap for pile rendering — largest count that settles in the bin. */
export const HEAP_RENDER_CEILING = 20;
/** Heap bin floor and ceiling in Pane coordinates. */
export const HEAP_BIN_FLOOR_Y = FLOOR_Y;
export const HEAP_BIN_EAST_X = FACE_X;
export const HEAP_BIN_CEILING_Y = PANE_HEIGHT;
/** Horizontal spawn for Ore entering the Heap bin from the Face. */
export const HEAP_SPAWN_X = FACE_X - ORE_SIZE / 2;
/** Hauler's hand height — one Ore radius above the bin floor. */
export const HEAP_GRAB_Y = HEAP_BIN_FLOOR_Y + ORE_SIZE / 2;
/** Carried Load offset from the sprite's left/bottom, east facing. */
export const HAULER_HAND_DX = 40;
export const HAULER_HAND_DY = 20;
/** Seeded RNG stream for Heap pile layout (#455). */
export const HEAP_PILE_SEED = 1;
/** Slot 0 hugs the Face column. */
export const HEAP_EAST_X = FACE_X - ORE_SIZE;
/** spawn → settled duration for Ore falling from the Face. */
export const ORE_FALL_MS = 250;
/** spawn height for falling Ore, mid-Face. */
export const ORE_SPAWN_BOTTOM = 56;

export const CART_MARK_X = CART_X + CART_WIDTH + 8;
const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
export const MINING_MARK_X = FACE_X - dwarfW;

/** The Hauler's resting and Unload station beside the Cart. */
export const HAULER_MARK_X = CART_MARK_X;
/** Heap bin west edge — independent of the Hauler's resting station. */
export const HEAP_BIN_WEST_X = CART_MARK_X + CART_WIDTH;

/** One walk speed for every Dwarf leg; sized so the widest possible lane
    (Cart mark to the Heap bin's east wall) crosses in one travel leg. */
export const HAULER_WALK_PX_PER_MS =
  (HEAP_BIN_EAST_X - CART_MARK_X) / (HAUL_TRAVEL_MS / 2);

/** Converts a pile body's Pane x into the sprite left where the Hauler's
    hands meet it, clamped inside the Tunnel. */
export function haulerStationFor(bodyX: number): number {
  const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
  return Math.max(
    CART_MARK_X,
    Math.min(
      Math.round(bodyX - HAULER_HAND_DX - ORE_SIZE / 2),
      HEAP_BIN_EAST_X - dwarfW,
    ),
  );
}

import {
  DWARF_FRAME_W,
  DWARF_SCALE,
  HAULER_MARK_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_ROW_HEIGHT,
  HEAP_SLOTS_PER_ROW,
  MINING_MARK_X,
  ORE_PITCH,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";

export type FallingOreDestination = "bag" | "heap";

function bagOrePosition(progress: number): { left: number; bottom: number } {
  const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
  const settledLeft = MINING_MARK_X + Math.round((dwarfW - ORE_SIZE) / 2);
  const settledBottom = HEAP_BOTTOM;
  return {
    left: Math.round(HEAP_EAST_X + (settledLeft - HEAP_EAST_X) * progress),
    bottom: Math.round(
      ORE_SPAWN_BOTTOM +
        (settledBottom - ORE_SPAWN_BOTTOM) * progress * progress,
    ),
  };
}

export function heapSlot(index: number): { left: number; bottom: number } {
  if (!Number.isInteger(index) || index < 0) {
    throw new Error(`Invalid heap slot index: ${index}`);
  }
  const row = Math.floor(index / HEAP_SLOTS_PER_ROW);
  const col = index % HEAP_SLOTS_PER_ROW;
  return {
    left: HEAP_EAST_X - col * ORE_PITCH,
    bottom: HEAP_BOTTOM + row * HEAP_ROW_HEIGHT,
  };
}

export function fallingOrePosition(
  destination: FallingOreDestination,
  slot: number,
  progress: number,
): { left: number; bottom: number } {
  if (progress < 0 || progress > 1) {
    throw new Error(`Invalid fall progress: ${progress}`);
  }
  if (destination === "bag") {
    return bagOrePosition(progress);
  }
  const settled = heapSlot(slot);
  return {
    left: Math.round(HEAP_EAST_X + (settled.left - HEAP_EAST_X) * progress),
    bottom: Math.round(
      ORE_SPAWN_BOTTOM +
        (settled.bottom - ORE_SPAWN_BOTTOM) * progress * progress,
    ),
  };
}

export function haulerPickupTargetX(heapLoads: number): number {
  if (!Number.isInteger(heapLoads) || heapLoads <= 0) {
    throw new Error(`Invalid heapLoads for hauler pickup: ${heapLoads}`);
  }
  const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
  const westMost = heapSlot(heapLoads - 1).left - dwarfW;
  return Math.max(HAULER_MARK_X, westMost);
}

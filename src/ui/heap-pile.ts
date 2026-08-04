import {
  DWARF_FRAME_W,
  DWARF_SCALE,
  HAULER_MARK_X,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  HEAP_ROW_HEIGHT,
  HEAP_SLOTS_PER_ROW,
  ORE_PITCH,
} from "./pane-layout";

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

export function haulerPickupTargetX(heapLoads: number): number {
  if (!Number.isInteger(heapLoads) || heapLoads <= 0) {
    throw new Error(`Invalid heapLoads for hauler pickup: ${heapLoads}`);
  }
  const dwarfW = DWARF_FRAME_W * DWARF_SCALE;
  const westMost = heapSlot(heapLoads - 1).left - dwarfW;
  return Math.max(HAULER_MARK_X, westMost);
}

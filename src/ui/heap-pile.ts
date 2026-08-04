import {
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

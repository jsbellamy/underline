import {
  DWARF_FRAME_W,
  DWARF_SCALE,
  HEAP_BOTTOM,
  HEAP_EAST_X,
  MINING_MARK_X,
  ORE_SIZE,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";

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

export function fallingOrePosition(
  _slot: number,
  progress: number,
): { left: number; bottom: number } {
  if (progress < 0 || progress > 1) {
    throw new Error(`Invalid fall progress: ${progress}`);
  }
  return bagOrePosition(progress);
}

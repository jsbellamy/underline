import {
  tunnelArtContentCenter,
  tunnelArtContentRadius,
  tunnelArtKeysUnder,
} from "../data/tunnel-art-pack";
import { ORE_SIZE } from "./pane-layout";
import { TUNNEL_ART_PACK } from "./tunnel-art";

export const HEAP_ORE_KEYS: readonly string[] = tunnelArtKeysUnder(
  TUNNEL_ART_PACK,
  "objects/ore/gold-",
);

export const HEAP_ORE_VARIANT_COUNT = HEAP_ORE_KEYS.length;

function heapOreKeyForIndex(variantIndex: number): string {
  if (!Number.isInteger(variantIndex)) {
    throw new Error(`Invalid heap ore variant index: ${variantIndex}`);
  }
  if (variantIndex < 0 || variantIndex >= HEAP_ORE_VARIANT_COUNT) {
    throw new Error(`Heap ore variant index out of range: ${variantIndex}`);
  }
  return HEAP_ORE_KEYS[variantIndex]!;
}

export function heapOreArtKey(variantIndex: number): string {
  return heapOreKeyForIndex(variantIndex);
}

export function heapOreRadius(variantIndex: number): number {
  return tunnelArtContentRadius(TUNNEL_ART_PACK, heapOreKeyForIndex(variantIndex));
}

export function heapOreContentCenter(variantIndex: number): {
  cx: number;
  cyFromBottom: number;
} {
  return tunnelArtContentCenter(
    TUNNEL_ART_PACK,
    heapOreKeyForIndex(variantIndex),
    ORE_SIZE,
  );
}

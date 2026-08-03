/** Adapted from Nightglass.

Source: nightglass/src/ui/sprites.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Manifest geometry validation only. No SPRITE_SOURCES / battlefield roles.
*/

export interface SpriteGeometry {
  frameSize: readonly [number, number];
  visualBounds: readonly [number, number, number, number];
  footAnchor: readonly [number, number];
}

type ManifestEntry = {
  frame_size?: unknown;
  visual_bounds?: unknown;
  foot_anchor?: unknown;
};

function isNumberPair(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    typeof value[0] === "number" &&
    typeof value[1] === "number"
  );
}

function isBoundsQuad(value: unknown): value is [number, number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((entry) => typeof entry === "number")
  );
}

export function geometryFromManifestEntry(
  spriteKey: string,
  entry: ManifestEntry | undefined,
): SpriteGeometry {
  if (!entry) {
    throw new Error(`Missing manifest entry for sprite key: ${spriteKey}`);
  }
  if (!isNumberPair(entry.frame_size)) {
    throw new Error(`Malformed frame_size for sprite key: ${spriteKey}`);
  }
  if (!isBoundsQuad(entry.visual_bounds)) {
    throw new Error(`Malformed visual_bounds for sprite key: ${spriteKey}`);
  }
  if (!isNumberPair(entry.foot_anchor)) {
    throw new Error(`Malformed foot_anchor for sprite key: ${spriteKey}`);
  }
  const [frameWidth, frameHeight] = entry.frame_size;
  const [left, top, right, bottom] = entry.visual_bounds;
  const [footX, footY] = entry.foot_anchor;
  if (frameWidth <= 0 || frameHeight <= 0) {
    throw new Error(`Invalid frame_size for sprite key: ${spriteKey}`);
  }
  if (
    left < 0 ||
    top < 0 ||
    right > frameWidth ||
    bottom > frameHeight ||
    right <= left ||
    bottom <= top
  ) {
    throw new Error(`visual_bounds exceed frame_size for sprite key: ${spriteKey}`);
  }
  if (footX !== Math.floor(frameWidth / 2) || footY !== frameHeight) {
    throw new Error(`foot_anchor must be bottom-centre for sprite key: ${spriteKey}`);
  }
  return {
    frameSize: entry.frame_size,
    visualBounds: entry.visual_bounds,
    footAnchor: entry.foot_anchor,
  };
}

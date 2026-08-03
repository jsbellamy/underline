/** Read `external-sprite-pack/0` manifests — pack owns frame order and relative paths. */

export type SpriteFacing = "east" | "west";

export interface ExternalSpriteFrame {
  relative_path: string;
  sha256: string;
  source_relative_path?: string;
  source_sha256?: string;
}

export interface ExternalSpriteAnimation {
  facings: Partial<Record<string, ExternalSpriteFrame[]>>;
  frame_count: number;
  note?: string;
}

export interface ExternalSpritePack {
  schema: string;
  id: string;
  layout: {
    frame_w: number;
    frame_h: number;
    facings: string[];
    [key: string]: unknown;
  };
  animations: Record<string, ExternalSpriteAnimation>;
  provenance?: Record<string, unknown>;
}

export interface DwarfLayout {
  frameW: number;
  frameH: number;
}

export function dwarfLayout(pack: ExternalSpritePack): DwarfLayout {
  const { frame_w: frameW, frame_h: frameH } = pack.layout;
  if (!(frameW > 0) || !(frameH > 0)) {
    throw new Error(`Invalid dwarf layout frame size: ${frameW}×${frameH}`);
  }
  return { frameW, frameH };
}

export function dwarfFramePaths(
  pack: ExternalSpritePack,
  animationId: string,
  facing: string,
): string[] {
  const animation = pack.animations[animationId];
  if (!animation) {
    throw new Error(`Unknown dwarf animation: ${animationId}`);
  }
  const frames = animation.facings[facing];
  if (!frames || frames.length === 0) {
    throw new Error(`Unknown dwarf facing "${facing}" for animation ${animationId}`);
  }
  return frames.map((frame) => frame.relative_path);
}

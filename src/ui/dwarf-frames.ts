/** Map `external-sprite-pack/0` relative_path → Vite URL via glob (no hard-coded frame paths). */

import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import {
  dwarfFramePaths,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";

const frameModules = import.meta.glob("../../assets/characters/dwarf/**/*.png", {
  eager: true,
  import: "default",
}) as Record<string, string>;

const urlByRelativePath = new Map<string, string>();
for (const [modulePath, url] of Object.entries(frameModules)) {
  const marker = "/assets/characters/dwarf/";
  const at = modulePath.lastIndexOf(marker);
  if (at < 0) {
    continue;
  }
  const relative = modulePath.slice(at + marker.length);
  urlByRelativePath.set(relative, url);
}

export function dwarfFrameUrl(relativePath: string): string {
  const url = urlByRelativePath.get(relativePath);
  if (!url) {
    throw new Error(`No Vite URL for dwarf frame: ${relativePath}`);
  }
  return url;
}

export function dwarfFrameUrlsFor(
  pack: ExternalSpritePack,
  animationId: string,
  facing: string,
): string[] {
  return dwarfFramePaths(pack, animationId, facing).map(dwarfFrameUrl);
}

export const DWARF_PACK = dwarfManifest as ExternalSpritePack;

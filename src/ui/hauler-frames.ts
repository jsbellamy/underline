/** Map `external-sprite-pack/0` relative_path → Vite URL via glob (no hard-coded frame paths). */

import haulerManifest from "../../assets/characters/hauler/manifest.json";
import {
  dwarfFramePaths,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";

const frameModules = import.meta.glob("../../assets/characters/hauler/**/*.png", {
  eager: true,
  import: "default",
}) as Record<string, string>;

const urlByRelativePath = new Map<string, string>();
for (const [modulePath, url] of Object.entries(frameModules)) {
  const marker = "/assets/characters/hauler/";
  const at = modulePath.lastIndexOf(marker);
  if (at < 0) {
    continue;
  }
  const relative = modulePath.slice(at + marker.length);
  urlByRelativePath.set(relative, url);
}

export function haulerFrameUrl(relativePath: string): string {
  const url = urlByRelativePath.get(relativePath);
  if (!url) {
    throw new Error(`No Vite URL for hauler frame: ${relativePath}`);
  }
  return url;
}

export function haulerFrameUrlsFor(
  pack: ExternalSpritePack,
  animationId: string,
  facing: string,
): string[] {
  return dwarfFramePaths(pack, animationId, facing).map(haulerFrameUrl);
}

export const HAULER_PACK = haulerManifest as ExternalSpritePack;

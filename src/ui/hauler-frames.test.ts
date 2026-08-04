import { describe, expect, it } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import {
  dwarfFramePaths,
  dwarfLayout,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";
import {
  HAULER_PACK,
  haulerFrameUrl,
  haulerFrameUrlsFor,
} from "./hauler-frames";

const DWARF_PACK = dwarfManifest as ExternalSpritePack;

describe("hauler-frames", () => {
  it("matches the Miner layout geometry for Tunnel mark arithmetic", () => {
    expect(dwarfLayout(HAULER_PACK)).toEqual(dwarfLayout(DWARF_PACK));
    expect(dwarfLayout(HAULER_PACK)).toEqual({ frameW: 26, frameH: 18 });
  });

  it("resolves walk/west frame URLs in manifest order and rejects unknown animations", () => {
    const urls = haulerFrameUrlsFor(HAULER_PACK, "walk", "west");
    expect(urls).toHaveLength(8);
    const paths = dwarfFramePaths(HAULER_PACK, "walk", "west");
    expect(urls).toEqual(paths.map(haulerFrameUrl));

    expect(() => haulerFrameUrlsFor(HAULER_PACK, "swing", "east")).toThrow(/animation/);
  });
});

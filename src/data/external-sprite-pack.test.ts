import { describe, expect, it } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import {
  dwarfFramePaths,
  dwarfLayout,
  type ExternalSpritePack,
} from "./external-sprite-pack";

describe("external-sprite-pack dwarf", () => {
  const pack = dwarfManifest as ExternalSpritePack;

  it("reads layout frame size from the on-disk external-sprite-pack/0 manifest", () => {
    expect(pack.schema).toBe("external-sprite-pack/0");
    expect(dwarfLayout(pack)).toEqual({ frameW: 26, frameH: 18 });
  });

  it("resolves swing/east frame paths from the manifest, not hard-coded strings", () => {
    const paths = dwarfFramePaths(pack, "swing", "east");
    expect(paths).toHaveLength(9);
    expect(paths[0]).toBe("swing/east/frame_000.png");
    expect(paths[8]).toBe("swing/east/frame_008.png");
  });

  it("resolves walk and idle facings from the same contract", () => {
    expect(dwarfFramePaths(pack, "idle", "east")).toEqual([
      "idle/east/frame_000.png",
    ]);
    expect(dwarfFramePaths(pack, "walk", "west")).toHaveLength(8);
    expect(dwarfFramePaths(pack, "walk", "west")[0]).toBe(
      "walk/west/frame_000.png",
    );
  });

  it("rejects unknown animation or facing", () => {
    expect(() => dwarfFramePaths(pack, "lunge", "east")).toThrow(/animation/);
    expect(() => dwarfFramePaths(pack, "swing", "north")).toThrow(/facing/);
  });
});

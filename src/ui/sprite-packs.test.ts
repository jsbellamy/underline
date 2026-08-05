import { describe, expect, it } from "vitest";
import {
  framePaths,
  dwarfLayout,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";
import {
  DWARF_PACK,
  HAULER_PACK,
  frameUrl,
  frameUrlsFor,
} from "./sprite-packs";

describe("sprite-packs", () => {
  it("exports DWARF_PACK and HAULER_PACK from on-disk manifests", () => {
    expect(DWARF_PACK.schema).toBe("external-sprite-pack/0");
    expect(DWARF_PACK.id).toBe("dwarf");
    expect(HAULER_PACK.schema).toBe("external-sprite-pack/0");
    expect(HAULER_PACK.id).toBe("hauler");
  });

  it("frameUrl resolves a known dwarf relative path and names character on miss", () => {
    const url = frameUrl("dwarf", "idle/east/frame_000.png");
    expect(url).toMatch(/frame_000\.png/);

    expect(() => frameUrl("dwarf", "missing/frame.png")).toThrow(
      /dwarf.*missing\/frame\.png/i,
    );
  });

  it("frameUrlsFor resolves walk/west for hauler in manifest order", () => {
    expect(dwarfLayout(HAULER_PACK)).toEqual(dwarfLayout(DWARF_PACK));
    expect(dwarfLayout(HAULER_PACK)).toEqual({ frameW: 26, frameH: 18 });

    const urls = frameUrlsFor("hauler", HAULER_PACK, "walk", "west");
    expect(urls).toHaveLength(8);
    const paths = framePaths(HAULER_PACK, "walk", "west");
    expect(urls).toEqual(paths.map((path) => frameUrl("hauler", path)));

    expect(() => frameUrlsFor("hauler", HAULER_PACK, "swing", "east")).toThrow(
      /animation/,
    );
  });

  it("frameUrlsFor matches prior dwarf and hauler URL lists for every animation and facing", () => {
    const packs: Array<{ character: string; pack: ExternalSpritePack; animations: string[] }> =
      [
        {
          character: "dwarf",
          pack: DWARF_PACK,
          animations: ["idle", "swing", "walk"],
        },
        {
          character: "hauler",
          pack: HAULER_PACK,
          animations: ["idle", "walk"],
        },
      ];

    for (const { character, pack, animations } of packs) {
      for (const animation of animations) {
        for (const facing of ["east", "west"] as const) {
          const paths = framePaths(pack, animation, facing);
          const urls = frameUrlsFor(character, pack, animation, facing);
          expect(urls).toHaveLength(paths.length);
          for (let i = 0; i < paths.length; i += 1) {
            expect(urls[i]).toBe(frameUrl(character, paths[i]!));
            expect(urls[i]).toMatch(/frame_\d{3}\.png/);
          }
        }
      }
    }
  });
});

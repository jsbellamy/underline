import { describe, expect, it } from "vitest";
import { geometryFromManifestEntry } from "./sprite-geometry";

describe("geometryFromManifestEntry", () => {
  it("accepts valid geometry with bottom-centre foot_anchor", () => {
    const geometry = geometryFromManifestEntry("dwarf-idle", {
      frame_size: [32, 48],
      visual_bounds: [4, 8, 28, 48],
      foot_anchor: [16, 48],
    });
    expect(geometry).toEqual({
      frameSize: [32, 48],
      visualBounds: [4, 8, 28, 48],
      footAnchor: [16, 48],
    });
  });

  it("requires foot_anchor to be bottom-centre of the frame", () => {
    expect(() =>
      geometryFromManifestEntry("bad", {
        frame_size: [32, 48],
        visual_bounds: [0, 0, 32, 48],
        foot_anchor: [0, 0],
      }),
    ).toThrow(/foot_anchor must be bottom-centre/);
  });

  it("rejects missing or malformed manifest geometry", () => {
    expect(() => geometryFromManifestEntry("missing", undefined)).toThrow(/Missing manifest/);
    expect(() =>
      geometryFromManifestEntry("bad", {
        frame_size: [32],
        visual_bounds: [0, 0, 1, 1],
        foot_anchor: [16, 48],
      }),
    ).toThrow(/frame_size/);
    expect(() =>
      geometryFromManifestEntry("bad", {
        frame_size: [32, 48],
        visual_bounds: [0, 0, 1],
        foot_anchor: [16, 48],
      }),
    ).toThrow(/visual_bounds/);
  });
});

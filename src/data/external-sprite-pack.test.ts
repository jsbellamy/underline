import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import haulerManifest from "../../assets/characters/hauler/manifest.json";
import {
  dwarfFramePaths,
  dwarfLayout,
  type ExternalSpritePack,
} from "./external-sprite-pack";

const HAULER_ROOT = resolve(import.meta.dirname, "../../assets/characters/hauler");

function sha256Hex(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

describe("external-sprite-pack hauler", () => {
  const pack = haulerManifest as ExternalSpritePack;

  it("declares idle and walk only, with expected frame counts and facings", () => {
    expect(pack.id).toBe("hauler");
    expect(pack.schema).toBe("external-sprite-pack/0");
    expect(Object.keys(pack.animations).sort()).toEqual(["idle", "walk"]);
    expect(pack.animations["swing"]).toBeUndefined();
    expect(pack.animations["idle"]?.frame_count).toBe(1);
    expect(pack.animations["walk"]?.frame_count).toBe(8);
    expect(dwarfFramePaths(pack, "idle", "east")).toEqual(["idle/east/frame_000.png"]);
    expect(dwarfFramePaths(pack, "idle", "west")).toEqual(["idle/west/frame_000.png"]);
    expect(dwarfFramePaths(pack, "walk", "east")).toHaveLength(8);
    expect(dwarfFramePaths(pack, "walk", "west")).toHaveLength(8);
  });

  it("hash-binds every shipped frame to its on-disk bytes", () => {
    for (const animation of Object.values(pack.animations)) {
      for (const facingFrames of Object.values(animation.facings)) {
        for (const frame of facingFrames ?? []) {
          const bytes = readFileSync(resolve(HAULER_ROOT, frame.relative_path));
          expect(sha256Hex(bytes)).toBe(frame.sha256);
        }
      }
    }
  });

  it("records external provenance outside the strip-acquisition pipeline", () => {
    expect(pack.provenance?.["kind"]).toBe("external");
    const note = String(pack.provenance?.["note"] ?? "");
    expect(note).toMatch(/strip-acquisition pipeline/i);
    expect(note).toMatch(/Gate score/i);
    expect(note).toMatch(/Do not treat as a Release asset/i);
  });
});

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

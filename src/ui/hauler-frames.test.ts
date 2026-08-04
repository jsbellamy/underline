import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import {
  dwarfFramePaths,
  dwarfLayout,
  type ExternalSpriteFrame,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";
import {
  HAULER_PACK,
  haulerFrameUrl,
  haulerFrameUrlsFor,
} from "./hauler-frames";

const HAULER_ROOT = resolve(import.meta.dirname, "../../assets/characters/hauler");
const DWARF_PACK = dwarfManifest as ExternalSpritePack;

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function decodePngRgba(buffer: Buffer): { width: number; height: number; rgba: Uint8Array } {
  let offset = 8;
  let width = 0;
  let height = 0;
  let colorType = 0;
  const idatChunks: Buffer[] = [];

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      colorType = data[9]!;
    } else if (type === "IDAT") {
      idatChunks.push(data);
    } else if (type === "IEND") {
      break;
    }
    offset += 12 + length;
  }

  if (colorType !== 6) {
    throw new Error(`Expected RGBA PNG, got color type ${colorType}`);
  }

  const raw = inflateSync(Buffer.concat(idatChunks));
  const bpp = 4;
  const stride = width * bpp;
  const rgba = new Uint8Array(width * height * 4);
  const row = new Uint8Array(stride);
  const prev = new Uint8Array(stride);
  let rawPos = 0;
  let outPos = 0;

  for (let y = 0; y < height; y++) {
    const filter = raw[rawPos++]!;
    for (let x = 0; x < stride; x++) {
      const byte = raw[rawPos++]!;
      switch (filter) {
        case 0:
          row[x] = byte;
          break;
        case 1:
          row[x] = (byte + (x >= bpp ? row[x - bpp]! : 0)) & 0xff;
          break;
        case 2:
          row[x] = (byte + prev[x]!) & 0xff;
          break;
        case 3: {
          const left = x >= bpp ? row[x - bpp]! : 0;
          row[x] = (byte + Math.floor((left + prev[x]!) / 2)) & 0xff;
          break;
        }
        case 4: {
          const left = x >= bpp ? row[x - bpp]! : 0;
          const up = prev[x]!;
          const upLeft = x >= bpp ? prev[x - bpp]! : 0;
          row[x] = (byte + paeth(left, up, upLeft)) & 0xff;
          break;
        }
        default:
          throw new Error(`Unknown PNG filter ${filter}`);
      }
    }
    rgba.set(row, outPos);
    prev.set(row);
    outPos += stride;
  }

  return { width, height, rgba };
}

function lowestOpaqueRow(rgba: Uint8Array, width: number, height: number): number {
  for (let y = height - 1; y >= 0; y--) {
    const rowStart = y * width * 4;
    for (let x = 0; x < width; x++) {
      if (rgba[rowStart + x * 4 + 3]! > 0) {
        return y;
      }
    }
  }
  return -1;
}

function bottomRowHasOpaquePixels(rgba: Uint8Array, width: number, height: number): boolean {
  const row = height - 1;
  const rowStart = row * width * 4;
  for (let x = 0; x < width; x++) {
    if (rgba[rowStart + x * 4 + 3]! > 0) {
      return true;
    }
  }
  return false;
}

function allFrames(pack: ExternalSpritePack): ExternalSpriteFrame[] {
  const frames: ExternalSpriteFrame[] = [];
  for (const animation of Object.values(pack.animations)) {
    for (const facingFrames of Object.values(animation.facings)) {
      if (facingFrames) {
        frames.push(...facingFrames);
      }
    }
  }
  return frames;
}

describe("hauler character pack", () => {
  it("ships 26×18 frames with feet on the shared bottom row and the Miner crop box", () => {
    expect(HAULER_PACK.layout["source_crop"]).toEqual([5, 9, 31, 27]);

    const frames = allFrames(HAULER_PACK);
    expect(frames).toHaveLength(18);

    for (const frame of frames) {
      const bytes = readFileSync(resolve(HAULER_ROOT, frame.relative_path));
      const { width, height, rgba } = decodePngRgba(bytes);
      expect(width).toBe(26);
      expect(height).toBe(18);
      expect(lowestOpaqueRow(rgba, width, height)).toBe(height - 1);
      expect(bottomRowHasOpaquePixels(rgba, width, height)).toBe(true);
    }
  });

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

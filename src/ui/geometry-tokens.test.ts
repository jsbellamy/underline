import { describe, expect, it } from "vitest";
import {
  DIG_RATE_LINE_HEIGHT,
  PANE_HEIGHT,
  PANE_WIDTH,
  TUNNEL_BAND_HEIGHT,
} from "./pane-layout";
import { DOCK_HEIGHT, DOCK_WIDTH } from "./dock-geometry";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("geometry tokens lockstep", () => {
  it("keeps CSS :root Pane and Dock tokens equal to the TypeScript constants", () => {
    const css = readFileSync(resolve("src/styles.css"), "utf8");
    expect(css).toMatch(new RegExp(`--pane-width:\\s*${PANE_WIDTH}px`));
    expect(css).toMatch(new RegExp(`--pane-height:\\s*${PANE_HEIGHT}px`));
    expect(css).toMatch(new RegExp(`--dig-rate-line-height:\\s*${DIG_RATE_LINE_HEIGHT}px`));
    expect(css).toMatch(new RegExp(`--tunnel-band-height:\\s*${TUNNEL_BAND_HEIGHT}px`));
    expect(css).toMatch(new RegExp(`--dock-width:\\s*${DOCK_WIDTH}px`));
    expect(css).toMatch(new RegExp(`--dock-height:\\s*${DOCK_HEIGHT}px`));
    // Pane outer height includes 1px border top+bottom under border-box.
    expect(DIG_RATE_LINE_HEIGHT + TUNNEL_BAND_HEIGHT).toBe(PANE_HEIGHT - 2);
  });
});

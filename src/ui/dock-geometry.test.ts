import { describe, expect, it } from "vitest";
import { DOCK_GAP_PX, DOCK_HEIGHT, DOCK_WIDTH, dockRect } from "./dock-geometry";

const PANE_WIDTH = 480;
const CENTER_OFFSET = (DOCK_WIDTH - PANE_WIDTH) / 2;

describe("dockRect", () => {
  const monitor = { x: 0, y: 0, width: 1920, height: 1080 };

  it("parks the Dock above a bottom-parked Pane with an 8px gap", () => {
    const pane = { x: 220, y: 732, width: 480, height: 112 };

    expect(dockRect(pane, monitor)).toEqual({
      x: 220 - CENTER_OFFSET,
      y: 732 - DOCK_GAP_PX - DOCK_HEIGHT,
      width: DOCK_WIDTH,
      side: "above",
      paneX: 220,
    });
  });

  it("parks the Dock below a top-parked Pane with an 8px gap", () => {
    const pane = { x: 200, y: 48, width: 480, height: 112 };

    expect(dockRect(pane, monitor)).toEqual({
      x: 200 - CENTER_OFFSET,
      y: 48 + 112 + DOCK_GAP_PX,
      width: DOCK_WIDTH,
      side: "below",
      paneX: 200,
    });
  });

  it("sizes the Dock to the workspace constants, not the Pane width", () => {
    const pane = { x: 0, y: 900, width: 480, height: 112 };

    expect(dockRect(pane, monitor).width).toBe(800);
  });

  it("centers the Dock on the Pane when the monitor has room", () => {
    const pane = { x: 200, y: 900, width: 480, height: 112 };

    const result = dockRect(pane, monitor);
    expect(result.x).toBe(200 - CENTER_OFFSET);
    expect(result.paneX).toBe(200);
  });

  it("clamps the dock to the right monitor edge and snaps the tile to stay centered", () => {
    const pane = { x: 1300, y: 900, width: 480, height: 112 };
    const maxDockX = monitor.width - DOCK_WIDTH;

    const result = dockRect(pane, monitor);
    expect(result.x).toBe(maxDockX);
    expect(result.paneX).toBe(maxDockX + CENTER_OFFSET);
    expect(result.paneX).not.toBe(pane.x);
  });

  it("flush-lefts the dock when the monitor is narrower than the dock workspace", () => {
    const tinyMonitor = { x: 50, y: 0, width: 600, height: 1080 };
    const pane = { x: 100, y: 900, width: 480, height: 112 };

    const result = dockRect(pane, tinyMonitor);
    expect(result.x).toBe(50);
    expect(result.paneX).toBe(50 + CENTER_OFFSET);
  });

  it("clamps the dock to the left monitor edge and snaps the tile to stay centered", () => {
    const pane = { x: 80, y: 900, width: 480, height: 112 };

    const result = dockRect(pane, monitor);
    expect(result.x).toBe(0);
    expect(result.paneX).toBe(CENTER_OFFSET);
    expect(result.paneX).not.toBe(pane.x);
  });
});

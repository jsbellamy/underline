/** Adapted from Nightglass dock-geometry.

Source: nightglass/src/ui/dock-geometry.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Adapted in place for Underline Pane vocabulary (tile → pane). Re-vendor from
upstream before further geometry edits.
*/

export const DOCK_WIDTH = 800;
export const DOCK_HEIGHT = 480;
export const DOCK_GAP_PX = 8;

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type DockSide = "above" | "below";

export interface DockRectResult {
  x: number;
  y: number;
  width: number;
  side: DockSide;
  /** Pane x after center + clamp-snap. Equals input pane.x when unclamped. */
  paneX: number;
}

export function dockRect(paneRect: Rect, monitorRect: Rect): DockRectResult {
  const midpoint = monitorRect.y + monitorRect.height / 2;
  const bottomParked = paneRect.y >= midpoint;
  const offset = (DOCK_WIDTH - paneRect.width) / 2;
  const proposedDockX = paneRect.x - offset;
  const minX = monitorRect.x;
  const maxX = monitorRect.x + monitorRect.width - DOCK_WIDTH;
  const x = Math.max(minX, Math.min(proposedDockX, maxX));
  const paneX = x + offset;

  if (bottomParked) {
    return {
      x,
      y: paneRect.y - DOCK_GAP_PX - DOCK_HEIGHT,
      width: DOCK_WIDTH,
      side: "above",
      paneX,
    };
  }

  return {
    x,
    y: paneRect.y + paneRect.height + DOCK_GAP_PX,
    width: DOCK_WIDTH,
    side: "below",
    paneX,
  };
}

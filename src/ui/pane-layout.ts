/** Adapted from Nightglass battle-tile-layout.

Source: nightglass/src/ui/battle-tile-layout.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Adapted for Underline Pane outer size. Composition (#318): no Dig Rate chrome —
Tunnel uses the full 480×112; Dig Rate / Ore / Ingots readouts are Dock-only.
Interim 24+86 constants remain until [Render the dwarf mining in the Pane](#321)
folds the full-band layout into the shell.
*/

/** Legacy chrome split — superseded by #318 (full-band Tunnel); remove in #321. */
export const DIG_RATE_LINE_HEIGHT = 24;
export const TUNNEL_BAND_HEIGHT = 86;
export const PANE_WIDTH = 480;
export const PANE_HEIGHT = 112;

# Underline — strip animation acquisition

Underline is a mining game. The game is TypeScript; the asset pipeline is Python.
The pipeline is what exists today: it takes a provider-rendered animation
**Strip**, recovers and slices it, and accepts or rejects it with deterministic
**Gates**. The terms below are the pipeline's; game vocabulary is added here as
it is settled.

Authority for the numbers behind these terms is
`docs/strip-acquisition-contract.md`.

## Language

**Strip**:
One provider render containing every Frame of a single animation side by side on
one logical grid, magenta-keyed.
_Avoid_: sheet, sprite sheet, filmstrip

**Frame**:
One animation pose within a Strip, occupying one logical Frame slot of the
declared width and height.
_Avoid_: cell (that means one logical pixel), panel

**Cell**:
One logical pixel of the recovered grid — the unit the Gates count.
_Avoid_: pixel (that means a raster pixel of the provider render)

**Gutter**:
The declared empty columns between Frames. It keeps subjects apart in the render;
it is not what slicing keys on.
_Avoid_: margin, padding

**Pitch**:
`frame_w + gutter` — the declared stride slicing advances by, so each Frame keeps
its position in the Strip. Slicing on content bounding boxes instead loses
position and impersonates motion as misalignment.
_Avoid_: stride, step

**Motion class**:
The declared kind of animation a Strip is (`idle`, `blob_idle`, `emissive`,
`airborne`, `walk`, `swing`). It carries its own Budgets plus the `grounded`,
`loops`, and `facing` properties. "Coherent" is not one number — it is per class.
_Avoid_: animation type, category

**Gate**:
One deterministic measurement with a pass/fail verdict: `silhouette_budget`,
`palette_drift_pass`, `min_pair_cohort_pass`, `displacement_pass`,
`baseline_row_stable`. Each exists to catch one failure mode and reports which
one tripped.
_Avoid_: check, validation

**Budget**:
The per-Motion-class threshold a Gate compares against, derived as
`ceil_to_0.01(worst measured value across that class's good Strips) + 0.02`. A
Gate that cannot separate good art from its Negative control has Budget `None`
and is excluded rather than widened.
_Avoid_: tolerance, limit

**Corpus**:
The scored sample set: PNGs in `inbox/` with declared Motion class and expected
verdict in `prompts/manifest.json`.
_Avoid_: dataset, test set

**Manifest-good Strip**:
A Strip the manifest declares `contract_expect: PASS` — a judgment about the art,
independent of whether it passes the Budgets currently being calibrated.
_Avoid_: passing strip

**Negative control**:
A Strip built to be rejected, proving a Gate still fires. Controls are fixed;
adding good Strips only widens Budgets toward them.
_Avoid_: bad sample, failing strip

**Declared anchor**:
The baseline row declared once for a Strip from Frame 0, rather than re-derived
per Frame as the lowest opaque row. Per-Frame derivation reads a stationary bat's
wingtip as an unstable baseline.
_Avoid_: ground line, floor

**Registration**:
The bounded shift search applied before comparing two Frames. Bounded, because an
unbounded best-shift search cancels the motion it is meant to measure and hands a
translation adversary a free pass.
_Avoid_: alignment (ambiguous with the alignment-sharpness probe)

**Known gap**:
A Gate that is inapplicable or unseparated for a Motion class or Strip, recorded
in the contract instead of papered over with a wider Budget.
_Avoid_: TODO, limitation

# Underline — strip animation acquisition

Underline is a mining game. The game is TypeScript; the asset pipeline is Python.
The pipeline is what exists today: it takes a provider-rendered animation
**Strip**, recovers and slices it, and accepts or rejects it with deterministic
**Gates**. The terms below are the pipeline's; game vocabulary is added here as
it is settled.

Authority for the numbers behind these terms is
`docs/strip-acquisition-contract.md`. The agent-ready AFK acceptance
implementation specification is
`docs/afk-acceptance-implementation-spec.md`.

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
`airborne`, `walk`, `swing`). It owns the animation's Acceptance profile plus
the `grounded`, `loops`, and `facing` properties. "Coherent" is not one number —
it is per class.
_Avoid_: animation type, category

**Acceptance profile**:
The per-Motion-class declaration of which Gates are Separated, Unseparated, or
Inapplicable, including a Budget for every applicable Gate.
_Avoid_: global acceptance criteria, animation-specific exceptions

**Gate**:
One deterministic measurement with an automatic-pass, agent-review, or hard-fail
outcome: `silhouette_budget`, `palette_drift_pass`, `min_pair_cohort_pass`,
`loop_closure_pass`, `displacement_pass`, `baseline_row_stable`. Each exists to
catch one failure mode and reports which one tripped.
_Avoid_: check, validation

**Budget**:
The per-Motion-class threshold separating automatic pass from agent review for
a Gate. It is derived inside the measured gap between Manifest-good Strips and
the Gate control; a Gate without a sufficient gap is Unseparated.
_Avoid_: tolerance, limit

**Gap allocation factor (α)**:
The fraction of the measured gap between the worst Manifest-good Strip and its
Gate control assigned to automatic-pass headroom; the remainder is the Review band.
_Avoid_: safety factor, confidence

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

**Gate control**:
A Negative control for one Motion class and exactly one applicable Gate. It must
fail its declared target Gate while passing every other applicable Gate, so its
measured value can calibrate only that Gate's Budget.
_Avoid_: identity control, multi-gate control, proxy control

**Isolation verdict**:
The result of judging one Attempt against its Gate-control specification:
`ISOLATED`, `NOT_ISOLATED`, or `INDETERMINATE`. Class-inapplicable Gates are
omitted; an undecidable class-applicable Gate makes the verdict indeterminate.
_Avoid_: acceptance verdict, pass/fail

**Gate-control specification**:
The stable declaration of the Motion-class/Gate isolation claim that a Gate
control must satisfy. It owns the history of Attempts and identifies at most one
Promotion.
_Avoid_: control attempt, promoted control

**Attempt**:
One immutable provider generation made against a Gate-control specification,
including its provenance, measurements, and outcome.
_Avoid_: candidate, retry

**Measurement run**:
One immutable scoring of an Attempt, identifying the Gate configuration and
producing raw metrics, per-Gate outcomes, and an Isolation verdict. Re-scoring
creates another Measurement run instead of replacing prior evidence.
_Avoid_: latest score, mutable report

**Promotion**:
The selection of one successful Attempt and Measurement run as the Gate control
for its Gate-control specification; it does not create a copy of the Strip.
_Avoid_: acceptance, canonical copy

**Review band**:
The measured interval above a Budget and below its Gate control. A Strip in this
interval requires an agent to judge the relevant visual defect instead of being
automatically accepted or rejected.
_Avoid_: grey area, soft fail, warning

**Gate review**:
One auditable agent judgment of one Gate in the Review band. It answers that
Gate's fixed visual question with `APPROVE`, `REJECT`, or `UNCERTAIN`; the Strip
is approved only when every Gate review approves.
_Avoid_: holistic review, manual override

**Review packet**:
The immutable, hash-bound evidence shown to a Gate reviewer: the Strip's
Gate-specific composite, its Budget-binding Manifest-good reference, and, for a
Separated Gate, its promoted Gate control.
_Avoid_: review screenshot, reviewer context

**Second review**:
A fresh Gate review of the same Review packet, performed without access to the
first review's verdict or rationale. It may use the same model and version but
has a distinct review identity.
_Avoid_: appeal, confirmation prompt

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

**Unseparated**:
A Motion-class/Gate pair whose Manifest-good and Gate-control populations do not
have the declared minimum gap required for an autonomous hard fail. The Gate
still automatically passes below its Budget but requires Review above it.
_Avoid_: overlapping, inconclusive

**Inapplicable**:
A Motion-class/Gate pair whose failure mode is not meaningful for that kind of
animation, so the Acceptance profile omits the Gate entirely.
_Avoid_: Unseparated, disabled

**Polish Bundle**:
The self-contained provenance and working context connecting one accepted
provider Strip to its Draft, Polished, and Release Frames.
_Avoid_: polish workspace, edit session

**Polish profile**:
A versioned, hash-bound set of fixed visual questions, editing rules, and
Motion-class overrides that tells an agent what finished art must preserve.
It supplies art-direction judgment; it is not a deterministic Gate.
_Avoid_: polish prompt, automatic accent detector

**Identity Lock**:
A subject-specific, Motion-class rule that compares declared canonical
structure, palette roles, and landmarks against an Attempt after bounded
registration. It is distinct from temporal coherence Gates: coherence compares
Frames within one Strip. Identity Lock compares every Frame to an external canonical identity.
The post-ingest identity anchor is validation evidence, not a generation canvas.
_Avoid_: identity anchor audit, canonical redraw check

**Generation source**:
The detailed, hash-bound provider artwork used as the image-edit base for a new
Motion-class Attempt. For dwarf walk and swing this is explicitly
`assets/first-room/dwarf/idle/provider/source.png`, declared in
`identity.json` → `generation_source` and copied by
`strip:polish seed --identity-declaration identity.json`. It is **not**
`identity.png`. It is distinct from the post-ingest identity anchor and must not
be reconstructed by upscaling a Release Frame. The selected Attempt’s
`provider/source.png` must remain the unmodified provider output — painting
Identity Lock cells into the transport raster to force Gate PASS is forbidden.
_Avoid_: identity anchor, Release Frame, visual reference, identity.png as edit canvas, provider lock-stamp

**Post-ingest identity anchor**:
The post-ingest Release Frame used by Identity Lock as external canonical
validation evidence. It is deliberately logical-resolution and must never be
upscaled or submitted as the generation source.
_Avoid_: generation source, edit source, seed canvas

**Identity feature**:
A visually defining subject detail such as the dwarf's lamp, eye, beard, belt,
or buckle. A pose may occlude an identity feature; this does not change the
post-ingest identity anchor used as external validation evidence.
_Avoid_: post-ingest identity anchor, generation source

**Draft Frame**:
An immutable-by-hash canonical Frame exported from the accepted provider Strip
before art edits.
_Avoid_: source frame, baseline frame

**Polished Frame**:
The editable RGB-only derivative of a Draft Frame; its occupancy and available
palette remain locked to the Draft sequence.
_Avoid_: work-in-progress frame, edited frame

**Release Frame**:
A Polished Frame made releasable only by automatic current-policy `PASS`.
_Avoid_: shipped frame, final frame

**Master Palette**:
The fixed cross-asset set of opaque RGB colors available to one Art Cohort.
_Avoid_: shared palette, color set

**Art Cohort**:
Assets approved together for one playable visual slice under one Master Palette,
scale, lighting, and shape language.
_Avoid_: asset batch, content pack

**Rendering Tile**:
One 16×16 world-rendering unit used to assemble cave edges and backgrounds.
_Avoid_: tile (ambiguous with Mineable Block), background cell

**Mineable Block**:
One atomic 32×32 mining target occupying a 2×2 area of Rendering Tiles.
_Avoid_: tile, ore tile, destructible tile

**Autotile Mask**:
The four-bit north/east/south/west neighbor signature selecting a Mineable Block
edge treatment. Bit values: north=1, east=2, south=4, west=8.
_Avoid_: bitmask, neighbor mask

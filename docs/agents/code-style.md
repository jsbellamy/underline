# Code style and test seams

How Underline code is structured and where its tests go. When the TDD skill
(`.cursor/skills/tdd/SKILL.md` on Cursor, `/tdd` elsewhere) asks which seams to
test, this document is the standing answer — no per-session seam negotiation is
needed unless the work falls outside it.

The game is **TypeScript**. Python is confined to the asset pipeline. A rule
below applies to whichever of the two it names.

## Layout

- `src/core/` — the headless simulation: pure TypeScript, no DOM, timers, audio,
  or asset imports. Time and RNG are injected.
- `src/data/` — content data plus its aggregate validator. Content modules
  import shared types only, never simulation internals; adding content must not
  require a core change.
- `src/ui/` — renderers driven by the simulation's serializable output. The
  presentation layer owns the mapping from domain events to sprites, effects, and
  audio; events never carry asset names.
- `pipeline/` — the Python asset pipeline: strip acquisition, grid recovery,
  slicing, and the coherence gates. Its contract is
  `docs/strip-acquisition-contract.md`.
- `tests/` — pytest for the pipeline. TypeScript tests live beside the code they
  cover.

The production gate library lives in `pipeline/strip.py`; grid-recovery primitives
are vendored in `pipeline/recovery.py`. Prototype runners under
`prototype/strip-coherence/` score the corpus and derive budgets against those modules.

## Seams

Test at these public boundaries, nowhere internal.

### TypeScript

- **Simulation seam** — the public entry point for constructing the simulation,
  issuing commands, advancing it by a caller-supplied duration, and reading a
  snapshot. Drive it with fixture content and a seeded random stream; pump time
  synchronously. **Chunk neutrality is itself a seam property**: where timing
  behavior is in scope, assert that many small advances and one large advance
  produce identical output.
- **Pure functions** — math with an independent worked example gets direct unit
  tests. Expected values come from the spec's worked numbers, never recomputed
  with the code's own formula.
- **Content validator** — data correctness is asserted in aggregate over the
  whole content object (id references resolving, registry completeness), not
  per-module.
- **Save seam** — tolerant recovery is tested through boot: a schema mismatch
  keeps durable progression and discards in-flight state; an unreadable save
  resets without crashing.
- **UI seam** — DOM integration tests mount a renderer, feed it snapshots and
  recorded events, and assert on the DOM.

### Python (asset pipeline)

- **Gate seam** — `coherence_report` / `coherence_split` over a frame list and a
  motion class. This is where a claim about "does this strip pass" is proved.
  Drive it with synthetic cell matrices built in the test, or with a named inbox
  sample; assert the verdict *and* which gate tripped, never just the boolean.
- **Slicing seam** — `slice_frames_pitch` / `recover_strip_cells`. Position in
  the strip is the load-bearing output: a test that only checks frame count will
  not catch the content-bbox regression that motivated pitch slicing. Assert
  offsets and per-frame extents.
- **Pure measurements** — `silhouette_diff`, `palette_drift`,
  `silhouette_pairwise`, `best_alignment_shift`, `displacement_gate_result` and
  friends get direct unit tests with hand-constructed grids whose expected value
  is worked out independently.
- **Characterization** — `tests/test_gates_characterization.py` pins current
  measured numbers on real samples. These are characterization tests, not
  specifications: any diff must be explained in the changing slice's PR body,
  never silently re-baselined.
- **Adversarial suite** — `adversarial.py` mutates a per-class baseline and
  asserts every `MUST_FAIL` mutation trips its intended gate. A new gate arrives
  with the mutation that proves it fires, or it is not evidenced.

## Style rules

### TypeScript

- Strict TypeScript; `npm run typecheck` is a live `package.json` script and must
  be green before publishing.
- Invalid commands throw — never silently no-op.
- The event vocabulary is append-only: add event types, never rename or repurpose
  one, so recorded fixtures and the presentation mapping stay valid.
- The snapshot is versioned and serializable; everything transient (DOM,
  animation, audio, timers, consumed events) stays out of it.
- Randomness is confined to persisted, seeded streams drawn in a fixed order, so
  a given seed reproduces byte-identical output. Tests assert exact numbers and
  timestamps against a pinned seed, never ranges.

### Python (asset pipeline)

- Python 3 with `from __future__ import annotations` and full type hints on
  public functions. Dataclasses are `frozen=True` where they carry contract data
  (`ClassBudget`, `StripLayout`).
- A module is either the gate library or a runner over it. A runner formats and
  reports; it does not own gate logic. If a runner needs a new measurement, the
  measurement goes in the library.
- Gates are **deterministic**: same cells in, same numbers out. No randomness, no
  wall-clock, no reliance on dict iteration order for a reported result. Tests
  assert exact values against a tolerance constant, never ranges chosen to make a
  run green.
- A gate that cannot separate good art from its negative control is set to `None`
  and recorded as a known gap — it is never widened until it passes everything.
  `airborne`'s excluded silhouette gate is the worked example.
- Budgets live in `MOTION_CLASSES` and must match
  `docs/strip-acquisition-contract.md`. Changing a number in one without the
  other is a documented-standard violation. Production Budget changes cite
  `npm run prototype:strip:alpha-budgets` output; the historical pre-α baseline
  remains `npm run prototype:strip:derive-budgets`.
- Invalid input raises — never silently return a passing verdict. A strip that
  cannot be recovered or sliced fails *before* the gates, and says which layer
  failed.
- One-off probe scripts are deleted once they have answered their question, and
  the answer is written into the pipeline's notes or the contract. Do not leave a
  probe behind as pseudo-infrastructure.

### Both

- A validator emits a machine-readable report alongside its human-readable
  output, on both the pass and fail paths. An agent reads gate results from the
  report; the printed lines are for people. A print-only validator forces every
  later reader to re-run the script or open the artifact it was measuring.
- Test names read as behavior specifications in `CONTEXT.md` vocabulary ("a slid
  frame trips the silhouette budget"), not implementation descriptions.
- Every abstraction, parameter, and hook is needed by the implementing issue's
  acceptance criteria (promoted from the Speculative Generality smell — a hard
  standard here, not a judgement call, because wave issues are precise enough to
  check against). An **interim** named by the issue body is the sanctioned form of
  building ahead; anything else built for an imagined future need is a violation.

# Issue tracker: GitHub Issues

Issues, PRDs, and wayfinder maps for this project live as **GitHub issues** on
`jsbellamy/underline`. Use the `gh` CLI (`gh issue …`, `gh api …`).

## Conventions

- One issue per unit of work; triage state is the issue's open/closed state plus labels.
- Long-form assets (research summaries, PRDs, prototype notes) live as Markdown
  files under `docs/` and are **linked** from the issue body, not pasted in.
- Comments and conversation history are GitHub issue comments.

## Dependency correctness

Every agent-ready issue has a `## Blocked by` section. Express predecessors once
in that section as `blocked_by: [numbers]`, omitting the field when there are
none, and mirror those predecessors as native GitHub blocking edges.

Split a prerequisite into its own blocking issue when it changes a different
system boundary or makes an advertised asset-only slice require pipeline code.
Do not hide such work in a prose “pipeline prerequisites” section. A single
combined issue is appropriate only when its Contract, Proof, slice type, and
`## Touches` honestly include both the prerequisite and the dependent change.

An orchestrator dispatches only when every blocking issue is closed. If a
missing prerequisite is discovered after dispatch, the implementer returns a
blocked report; the orchestrator repairs the dependency graph or issue scope
before redispatching.

## Writing `## Touches`

Anchor at the symbol, never the file: `pipeline/strip.py :: layout_for_motion_class`
is a manifest an implementer can resolve with `npm run agents:anchors`, while a
bare file name silently costs it the whole module on every round trip. Prose
anchors ("the `layout = _corpus_layout()` call preceding …") are legitimate when
no symbol names the site, but they resolve by hand — spend them deliberately.

When a slice changes how a library symbol fails — a new exception, a re-typed
one, a new reason code — the manifest names its CLI handler
(`pipeline/<module>_cli.py`) and that CLI's test module too. The library and the
handler that catches it are one seam; splitting them across the manifest
boundary is how a slice ships a library change that crashes the CLI.

## When a skill says "publish to the issue tracker"

Create a new issue with `gh issue create`. Put long-form artifacts in `docs/` and
link them from the body.

## When a skill says "fetch the relevant ticket"

`gh issue view <number>`. The user will normally pass its number or URL.

## Wayfinding operations

The `wayfinder:*` labels below **do not exist in this repo yet**. Create the ones
you need with `gh label create <name> --repo jsbellamy/underline` before first
use rather than silently reusing a different label.

- **Map**: a single issue labelled `wayfinder:map`. Its body holds Destination,
  Notes, Decisions so far, Not yet specified, and Out of scope. Find it with
  `gh issue list --label wayfinder:map`.
- **Child ticket**: a **sub-issue** of the map (GitHub native sub-issues), holding
  one question in its body. It carries exactly one type label:
  `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or
  `wayfinder:task`.
  - Attach: `gh api repos/jsbellamy/underline/issues/<map>/sub_issues -F sub_issue_id=<child_id>`
    where `<child_id>` is the child's REST id (`gh api repos/jsbellamy/underline/issues/<n> --jq .id`).
  - List children: `gh api repos/jsbellamy/underline/issues/<map>/sub_issues`.
- **Blocking**: wire native issue dependencies as described above and mirror
  them in the issue's `## Blocked by` `blocked_by: [numbers]` field. A ticket is
  unblocked when every blocker is closed.
  (Sub-issues give the parent its completion rollup, but do not express blocking
  between siblings.)
  - Add a blocker: `gh api repos/jsbellamy/underline/issues/<N>/dependencies/blocked_by -F issue_id=<blocker REST id>`
    (`-F` is load-bearing — `issue_id` must arrive as a typed integer; `-f` sends
    a string and the API returns 422. The REST id comes from
    `gh api repos/jsbellamy/underline/issues/<M> -q .id`.)
- **Frontier**: the map's open sub-issues that are unblocked (every native
  blocker closed; the `## Blocked by` field is the body companion)
  and unclaimed (no assignee); lowest number wins.
- **Claim**: assign the ticket to the driving dev before any work —
  `gh issue edit <n> --add-assignee @me`. An open, unassigned sub-issue is unclaimed.
- **Resolve**: post the answer as a comment (`gh issue comment <n>`), close the
  issue (`gh issue close <n> --reason completed`), and append a one-line gist plus
  the issue link to the map body's "Decisions so far" section
  (`gh issue edit <map> --body-file …`).

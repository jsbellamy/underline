# Triage Labels

The skills speak in terms of five canonical triage roles. This table maps them to
the strings used by this repo's GitHub tracker.

| Canonical role | Tracker label | Exists? | Meaning |
| --- | --- | --- | --- |
| `needs-triage` | `needs-triage` | not yet | Maintainer needs to evaluate this issue |
| `needs-info` | `needs-info` | not yet | Waiting on reporter for more information |
| `ready-for-agent` | `ready-for-agent` | yes | Fully specified and ready for an AFK agent |
| `ready-for-human` | `ready-for-human` | not yet | Requires human implementation |
| `wontfix` | `wontfix` | yes | Will not be actioned |

When a skill mentions a role, use the corresponding tracker label from this
table.

Labels marked "not yet" have not been created on `jsbellamy/underline`. Create
one with `gh label create <name> --repo jsbellamy/underline` on first use rather
than substituting a different label.

## CI-behavior labels

Not a triage role: this label changes what `.github/workflows/ci.yml` does on
a PR, rather than routing the issue itself.

| Label | Exists? | Meaning |
| --- | --- | --- |
| `evaluator-change` | yes | Declares that this PR's `external-acceptance` job divergence (main's verdict vs. the candidate branch's own verdict for a bundle) is a deliberate evaluator change, not an asset PR silently changing its own judge. The job reports the divergence as an annotation and passes instead of failing (issue #232, C3). |

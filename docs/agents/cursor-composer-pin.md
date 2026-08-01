# Cursor Composer standard pin

**Standard pin** is the only Composer 2.5 slug Underline uses:

```text
composer-2.5[fast=false]
```

Bare `composer-2.5` and `composer-2.5-fast` resolve to fast mode and bill as
`composer-2.5-fast`. Always spell the bracket form; never shorten it.

## Orchestrator (parent chat)

1. Select **Composer 2.5** with **fast=false** in the model picker before sending.
2. Spawn pinned subagents by **subagent name** on the Task tool — omit `model`.
3. Use the named subagent (`issue-implementer-code`, `code-review-spec`, …) — not
   `generalPurpose` with an inline model.

## Agent frontmatter

Every pinned agent under `.cursor/agents/`:

```yaml
model: "composer-2.5[fast=false]"
```

Never edit another agent's frontmatter `model` line.

## Hooks

`preToolUse` on Task (`.cursor/hooks/gate-task-spawn.sh`) rewrites every Composer
Task spawn to the standard pin. User-level wiring: `~/.cursor/hooks.json`.

## Pinned subagents

| Subagent | Role |
| -------- | ---- |
| `issue-implementer-code` | Code-slice implementer |
| `issue-implementer-asset` | Asset-slice implementer |
| `code-review-standards` | `/code-review` Standards axis |
| `code-review-spec` | `/code-review` Spec axis |
| `gate-blind-review` | Promotion blind gate audit |

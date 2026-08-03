# Cursor Composer standard pin

**Standard pin** is Composer 2.5 with **fast=false**. In the model picker, select
**Composer 2.5** and turn fast off. In logs and docs, refer to that pin as:

```text
composer-2.5[fast=false]
```

Bare `composer-2.5` and `composer-2.5-fast` resolve to fast mode and bill as
`composer-2.5-fast`. The bracket form is a **human label only** — it is not a
valid Task spawn slug.

## Task API shape

The Task tool accepts only bare slugs (`composer-2.5`, `composer-2.5-fast`, …).
Standard mode must be expressed as slug **plus** `model_params`:

```json
{
  "model": "composer-2.5",
  "model_params": [{ "id": "fast", "value": "false" }]
}
```

Use this shape when spawning a Task with an inline `model` (pinned subagents
omit `model` and inherit from agent frontmatter).

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

Keep the bracket form in frontmatter so the agent settings UI shows **Composer
2.5** (standard), not **Composer 2.5 Fast**. Bare `composer-2.5` in frontmatter
selects fast mode in the UI.

## Pinned subagents

| Subagent | Role |
| -------- | ---- |
| `issue-implementer-code` | Code-slice implementer |
| `issue-implementer-asset` | Asset-slice implementer |
| `code-review-standards` | `/code-review` Standards axis |
| `code-review-spec` | `/code-review` Spec axis |
| `gate-blind-review` | Promotion blind gate audit |

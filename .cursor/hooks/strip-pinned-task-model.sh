#!/usr/bin/env bash
# Remove inline Task model overrides for pinned custom subagents so frontmatter pins apply.
set -euo pipefail

input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name // empty')
subagent_type=$(echo "$input" | jq -r '.tool_input.subagent_type // empty')
inline_model=$(echo "$input" | jq -r '.tool_input.model // empty')

pinned='^(code-review-standards|code-review-spec|issue-implementer-code|issue-implementer-asset|gate-blind-review)$'

if [[ "$tool_name" == "Task" ]] && [[ "$subagent_type" =~ $pinned ]] && [[ -n "$inline_model" ]]; then
  echo "$input" | jq '{
    permission: "allow",
    agent_message: (
      "Stripped inline Task model override for pinned subagent "
      + .tool_input.subagent_type
      + "; using agent frontmatter composer-2.5[fast=false]."
    ),
    updated_input: (.tool_input | del(.model))
  }'
  exit 0
fi

echo '{"permission":"allow"}'

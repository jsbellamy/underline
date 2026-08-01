#!/usr/bin/env bash
# Gate Task spawns: deny fast inline models, strip pinned overrides, deny fast parents.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/composer-2.5-mode.sh
source "$script_dir/lib/composer-2.5-mode.sh"

input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name // empty')

if [[ "$tool_name" != "Task" ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

subagent_type=$(echo "$input" | jq -r '.tool_input.subagent_type // empty')
inline_model=$(echo "$input" | jq -r '.tool_input.model // empty')
parent_model=$(echo "$input" | jq -r '.model // empty')
parent_params=$(echo "$input" | jq -c '.model_params // []')

deny_task() {
  local detail="$1"
  jq -n --arg d "$detail" '{
    permission: "deny",
    user_message: ("Task blocked: Composer 2.5 fast mode is disabled. " + $d),
    agent_message: ("Never spawn subagents on Composer 2.5 fast. " + $d)
  }'
  exit 0
}

if [[ -n "$inline_model" ]]; then
  if is_pinned_subagent "$subagent_type"; then
    echo "$input" | jq '{
      permission: "allow",
      agent_message: (
        "Stripped inline Task model for pinned subagent "
        + .tool_input.subagent_type
        + "; using frontmatter composer-2.5[fast=false]."
      ),
      updated_input: (.tool_input | del(.model))
    }'
    exit 0
  fi

  inline_mode=$(composer_25_mode "$inline_model" "[]")
  if [[ "$inline_mode" == fast ]]; then
    deny_task "Inline Task model was ${inline_model}."
  fi
fi

if is_composer_25_fast "$parent_model" "$parent_params"; then
  deny_task "Parent chat is on Composer 2.5 fast; subagents would inherit it."
fi

echo '{"permission":"allow"}'

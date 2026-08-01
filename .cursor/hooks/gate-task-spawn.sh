#!/usr/bin/env bash
# Gate Task spawns: rewrite every Composer 2.5 Task to composer-2.5 + fast=false param.
# preToolUse is the only hook that can change the model; never deny here.
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
inline_params=$(echo "$input" | jq -c '.tool_input.model_params // []')
parent_model=$(echo "$input" | jq -r '.model // empty')
parent_params=$(echo "$input" | jq -c '.model_params // []')

allow_task_with_standard_composer() {
  local message="$1"
  echo "$input" | jq \
    --arg m "$COMPOSER_25_API_SLUG" \
    --arg msg "$message" \
    --argjson params "$COMPOSER_25_STANDARD_PARAMS" \
    '{
      permission: "allow",
      agent_message: $msg,
      updated_input: (.tool_input | .model = $m | .model_params = $params)
    }'
  exit 0
}

# Pinned agents always get the spawnable standard pin (frontmatter slug alone is not enough).
if is_pinned_subagent "$subagent_type"; then
  if task_input_is_standard_composer_25 "$inline_model" "$inline_params"; then
    echo '{"permission":"allow"}'
    exit 0
  fi
  allow_task_with_standard_composer \
    "Rewrote Task to ${COMPOSER_25_STANDARD_MODEL} (${COMPOSER_25_API_SLUG} + fast=false) for pinned subagent ${subagent_type}."
fi

if [[ -n "$inline_model" ]]; then
  if is_composer_25_family "$inline_model" "$inline_params"; then
    if task_input_is_standard_composer_25 "$inline_model" "$inline_params"; then
      echo '{"permission":"allow"}'
    else
      allow_task_with_standard_composer \
        "Rewrote inline Task model ${inline_model} to ${COMPOSER_25_STANDARD_MODEL}."
    fi
  else
    echo '{"permission":"allow"}'
  fi
  exit 0
fi

# No inline model: inherit path. Composer parents (fast or standard) → force standard.
if is_composer_25_family "$parent_model" "$parent_params"; then
  allow_task_with_standard_composer \
    "Injected ${COMPOSER_25_STANDARD_MODEL} because Task had no inline model on a Composer parent."
fi

echo '{"permission":"allow"}'

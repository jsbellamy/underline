#!/usr/bin/env bash
# Gate Task spawns: rewrite every Composer 2.5 Task to composer-2.5[fast=false].
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
parent_model=$(echo "$input" | jq -r '.model // empty')
parent_params=$(echo "$input" | jq -c '.model_params // []')

allow_task_with_model() {
  local model="$1"
  local message="$2"
  echo "$input" | jq --arg m "$model" --arg msg "$message" '{
    permission: "allow",
    agent_message: $msg,
    updated_input: (.tool_input | .model = $m)
  }'
  exit 0
}

# Pinned agents always get an explicit standard slug (frontmatter alone is not enough).
if is_pinned_subagent "$subagent_type"; then
  if [[ "$inline_model" == "$COMPOSER_25_STANDARD_MODEL" ]]; then
    echo '{"permission":"allow"}'
    exit 0
  fi
  allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
    "Rewrote Task model to ${COMPOSER_25_STANDARD_MODEL} for pinned subagent ${subagent_type}."
fi

if [[ -n "$inline_model" ]]; then
  case "$(composer_25_mode "$inline_model" "[]")" in
    fast)
      allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
        "Rewrote inline Task model ${inline_model} to ${COMPOSER_25_STANDARD_MODEL}."
      ;;
    standard)
      if [[ "$inline_model" == "$COMPOSER_25_STANDARD_MODEL" ]]; then
        echo '{"permission":"allow"}'
      else
        allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
          "Normalized inline Task model ${inline_model} to ${COMPOSER_25_STANDARD_MODEL}."
      fi
      ;;
    *)
      echo '{"permission":"allow"}'
      ;;
  esac
  exit 0
fi

# No inline model: inherit path. Composer parents (fast or standard) → force standard.
if is_composer_25_family "$parent_model" "$parent_params"; then
  allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
    "Injected ${COMPOSER_25_STANDARD_MODEL} because Task had no inline model on a Composer parent."
fi

echo '{"permission":"allow"}'

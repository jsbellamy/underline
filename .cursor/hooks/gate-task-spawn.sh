#!/usr/bin/env bash
# Gate Task spawns: deny fast models and force explicit composer-2.5[fast=false].
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
    agent_message: ("Never spawn subagents on Composer 2.5 fast. Use composer-2.5[fast=false] or a non-Composer model. " + $d)
  }'
  exit 0
}

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

if is_pinned_subagent "$subagent_type"; then
  if [[ -n "$inline_model" ]] && is_composer_25_fast "$inline_model" "[]"; then
    deny_task "Pinned subagent ${subagent_type} cannot use inline fast model ${inline_model}."
  fi
  allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
    "Forced ${COMPOSER_25_STANDARD_MODEL} for pinned subagent ${subagent_type}."
fi

if [[ -n "$inline_model" ]]; then
  inline_mode=$(composer_25_mode "$inline_model" "[]")
  case "$inline_mode" in
    fast)
      deny_task "Inline Task model was ${inline_model}."
      ;;
    standard)
      echo '{"permission":"allow"}'
      exit 0
      ;;
    other)
      echo '{"permission":"allow"}'
      exit 0
      ;;
    *)
      allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
        "Rewrote ambiguous inline Task model ${inline_model} to ${COMPOSER_25_STANDARD_MODEL}."
      ;;
  esac
fi

if is_composer_25_fast "$parent_model" "$parent_params"; then
  deny_task "Parent chat is on Composer 2.5 fast; subagents would inherit it."
fi

if is_composer_25_family "$parent_model" "$parent_params"; then
  allow_task_with_model "$COMPOSER_25_STANDARD_MODEL" \
    "Injected ${COMPOSER_25_STANDARD_MODEL} because Task had no inline model on a Composer parent."
fi

echo '{"permission":"allow"}'

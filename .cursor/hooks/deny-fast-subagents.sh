#!/usr/bin/env bash
# subagentStart cannot rewrite models (allow/deny only). Deny if a Composer subagent
# still starts in fast mode after gate-task-spawn.sh should have injected fast=false.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/composer-2.5-mode.sh
source "$script_dir/lib/composer-2.5-mode.sh"

input=$(cat)
model=$(echo "$input" | jq -r '.model // empty')
params=$(echo "$input" | jq -c '.model_params // []')

if is_composer_25_fast "$model" "$params"; then
  jq -n --arg m "$model" --arg label "$COMPOSER_25_STANDARD_MODEL" '{
    permission: "deny",
    user_message: (
      "Composer 2.5 Fast subagent blocked. Expected " + $label
      + " (composer-2.5 with fast=false). Resolved subagent model: " + $m
    )
  }'
  exit 0
fi

echo '{"permission":"allow"}'

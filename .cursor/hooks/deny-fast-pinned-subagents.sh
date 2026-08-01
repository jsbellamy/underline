#!/usr/bin/env bash
# Fail closed on pinned custom subagents that resolve to Composer 2.5 fast mode.
set -euo pipefail

input=$(cat)
subagent_model=$(echo "$input" | jq -r '.subagent_model // empty')

if [[ -z "$subagent_model" ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

is_fast=false
case "$subagent_model" in
  *fast=true* | *"[fast=true]"* | composer-2.5-fast | *composer-2.5-fast*)
    is_fast=true
    ;;
  composer-2.5 | composer-2.5[] | *"[fast=false]"* | *fast=false*)
    is_fast=false
    ;;
  composer-2.5*)
    # Bare composer-2.5 without an explicit non-fast pin defaults to fast.
    is_fast=true
    ;;
esac

if $is_fast; then
  jq -n --arg m "$subagent_model" '{
    permission: "deny",
    user_message: (
      "Pinned subagent blocked: requires Composer 2.5 standard (fast=false). "
      + "Resolved model was " + $m + ". Spawn by subagent name only; do not pass an inline Task model."
    )
  }'
  exit 0
fi

echo '{"permission":"allow"}'

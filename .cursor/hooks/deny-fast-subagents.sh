#!/usr/bin/env bash
# Fail closed: deny every subagent that resolves to Composer 2.5 fast mode.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/composer-2.5-mode.sh
source "$script_dir/lib/composer-2.5-mode.sh"

input=$(cat)
subagent_type=$(echo "$input" | jq -r '.subagent_type // empty')
subagent_model=$(echo "$input" | jq -r '.subagent_model // empty')
parent_model=$(echo "$input" | jq -r '.model // empty')
parent_params=$(echo "$input" | jq -c '.model_params // []')

deny() {
  local detail="$1"
  jq -n --arg d "$detail" '{
    permission: "deny",
    user_message: ("Subagent blocked: Composer 2.5 fast mode is disabled. " + $d)
  }'
  exit 0
}

if [[ -n "$subagent_model" ]]; then
  mode=$(composer_25_mode "$subagent_model" "[]")
  case "$mode" in
    fast)
      if is_pinned_subagent "$subagent_type" && is_bare_composer_25_slug "$subagent_model"; then
        echo '{"permission":"allow"}'
        exit 0
      fi
      deny "Resolved subagent_model was ${subagent_model}."
      ;;
    standard)
      echo '{"permission":"allow"}'
      exit 0
      ;;
    other)
      echo '{"permission":"allow"}'
      exit 0
      ;;
    unknown)
      if is_pinned_subagent "$subagent_type"; then
        deny "Pinned agent ${subagent_type} reported an unclassified model slug."
      fi
      ;;
  esac
fi

if is_pinned_subagent "$subagent_type"; then
  deny "Pinned agent ${subagent_type} did not report subagent_model (fail closed)."
fi

if is_composer_25_fast "$parent_model" "$parent_params"; then
  deny "Parent chat is on Composer 2.5 fast and subagent_model was not reported."
fi

parent_mode=$(composer_25_mode "$parent_model" "$parent_params")
if [[ "$parent_mode" == fast ]]; then
  deny "Parent resolves to Composer 2.5 fast."
fi

echo '{"permission":"allow"}'

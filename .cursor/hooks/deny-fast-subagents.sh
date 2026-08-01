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
workspace_root=$(workspace_root_from_json "$input")

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
      if pinned_agent_allows_bare_slug "$subagent_type" "$workspace_root" \
        && [[ "$subagent_model" == "composer-2.5" || "$subagent_model" == "composer-2.5[]" ]]; then
        # Cursor often reports bare composer-2.5 for frontmatter-pinned standard agents.
        # preToolUse should have forced composer-2.5[fast=false]; allow only with frontmatter proof.
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
      deny "Subagent reported an unclassified model slug (${subagent_model})."
      ;;
  esac
fi

if is_pinned_subagent "$subagent_type"; then
  if pinned_agent_frontmatter_standard "$subagent_type" "$workspace_root"; then
    echo '{"permission":"allow"}'
    exit 0
  fi
  deny "Pinned agent ${subagent_type} did not report subagent_model and frontmatter is not composer-2.5[fast=false]."
fi

if is_composer_25_fast "$parent_model" "$parent_params"; then
  deny "Parent chat is on Composer 2.5 fast and subagent_model was not reported."
fi

if is_composer_25_family "$parent_model" "$parent_params"; then
  deny "Composer parent spawned a subagent without reporting subagent_model (fail closed)."
fi

echo '{"permission":"allow"}'

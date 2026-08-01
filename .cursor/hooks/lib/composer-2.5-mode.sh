#!/usr/bin/env bash
# Classify Composer 2.5 model slugs and model_params for hook gating.
# Sourced by other hook scripts; not executed directly.

readonly COMPOSER_25_STANDARD_MODEL='composer-2.5[fast=false]'

composer_25_mode() {
  local slug="${1:-}"
  local params="${2:-[]}"

  if [[ -n "$params" && "$params" != "null" && "$params" != "[]" ]]; then
    if echo "$params" | jq -e 'any(.[]; .id == "fast" and .value == "true")' >/dev/null 2>&1; then
      echo fast
      return 0
    fi
    if echo "$params" | jq -e 'any(.[]; .id == "fast" and .value == "false")' >/dev/null 2>&1; then
      echo standard
      return 0
    fi
  fi

  case "$slug" in
    *composer-2.5-fast* | composer-2.5-fast)
      echo fast
      ;;
    *"[fast=true]"* | *fast=true*)
      echo fast
      ;;
    *"[fast=false]"* | *fast=false*)
      echo standard
      ;;
    composer-2.5 | composer-2.5[])
      # Cursor default: bare composer-2.5 selects fast mode.
      echo fast
      ;;
    composer-2.5*)
      echo fast
      ;;
    '')
      echo unknown
      ;;
    *)
      echo other
      ;;
  esac
}

is_composer_25_fast() {
  [[ "$(composer_25_mode "$1" "$2")" == fast ]]
}

is_composer_25_standard() {
  [[ "$(composer_25_mode "$1" "$2")" == standard ]]
}

is_composer_25_family() {
  case "$(composer_25_mode "$1" "$2")" in
    fast | standard) return 0 ;;
    *) return 1 ;;
  esac
}

is_pinned_subagent() {
  [[ "$1" =~ ^(code-review-standards|code-review-spec|issue-implementer-code|issue-implementer-asset|gate-blind-review)$ ]]
}

workspace_root_from_json() {
  local input="$1"
  echo "$input" | jq -r '.workspace_roots[0] // empty'
}

pinned_agent_frontmatter_standard() {
  local subagent_type="$1"
  local workspace_root="$2"
  local agent_file=""

  if [[ -z "$subagent_type" || -z "$workspace_root" ]]; then
    return 1
  fi

  agent_file="${workspace_root}/.cursor/agents/${subagent_type}.md"
  if [[ ! -f "$agent_file" ]]; then
    return 1
  fi

  if grep -Eiq '^[[:space:]]*model:[[:space:]]*"?composer-2\.5\[fast=false\]"?' "$agent_file"; then
    return 0
  fi

  return 1
}

pinned_agent_allows_bare_slug() {
  local subagent_type="$1"
  local workspace_root="$2"

  is_pinned_subagent "$subagent_type" && pinned_agent_frontmatter_standard "$subagent_type" "$workspace_root"
}

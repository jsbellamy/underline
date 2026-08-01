#!/usr/bin/env bash
# Classify Composer 2.5 model slugs and model_params for hook gating.
# Sourced by other hook scripts; not executed directly.

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

is_pinned_subagent() {
  [[ "$1" =~ ^(code-review-standards|code-review-spec|issue-implementer-code|issue-implementer-asset|gate-blind-review)$ ]]
}

# Cursor subagentStart often reports bare composer-2.5 even when agent frontmatter
# pins composer-2.5[fast=false] and runtime runs standard mode.
is_bare_composer_25_slug() {
  case "$1" in
    composer-2.5 | composer-2.5[])
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

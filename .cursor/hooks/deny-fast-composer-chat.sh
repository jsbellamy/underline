#!/usr/bin/env bash
# Block user prompts when the composer chat is on Composer 2.5 fast mode.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/composer-2.5-mode.sh
source "$script_dir/lib/composer-2.5-mode.sh"

input=$(cat)
model=$(echo "$input" | jq -r '.model // empty')
params=$(echo "$input" | jq -c '.model_params // []')

mode=$(composer_25_mode "$model" "$params")
if [[ "$mode" == fast ]]; then
  jq -n --arg m "$model" '{
    continue: false,
    user_message: (
      "Composer 2.5 Fast is disabled in this workspace. "
      + "Switch the chat model to Composer 2.5 standard (fast=false) before sending. "
      + "Resolved chat model: " + $m
    )
  }'
  exit 0
fi

echo '{"continue":true}'

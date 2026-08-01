#!/usr/bin/env bash
# subagentStart cannot rewrite models (allow/deny only). preToolUse gate-task-spawn.sh
# already injects composer-2.5[fast=false] on every Composer Task spawn — allow through.
set -euo pipefail

echo '{"permission":"allow"}'

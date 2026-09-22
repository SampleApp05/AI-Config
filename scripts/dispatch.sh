#!/usr/bin/env bash
set -euo pipefail

workflow_root="$(cd "$(dirname "$0")/.." && pwd)"
export WORKFLOW_SHARED_ROOT="$workflow_root"
exec python3 "$workflow_root/scripts/dispatch.py" "$@"

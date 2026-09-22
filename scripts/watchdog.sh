#!/usr/bin/env bash
set -euo pipefail

workflow_root="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$workflow_root/scripts/watchdog.py" "$@"

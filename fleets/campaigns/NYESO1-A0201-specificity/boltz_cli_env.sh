#!/usr/bin/env bash
# Map Cursor Cloud secret boltz_api_key -> BOLTZ_API_KEY for boltz-api SDK / curl.
# Usage: source "$(dirname "$0")/boltz_cli_env.sh"

set -euo pipefail

export BOLTZ_API_KEY="${BOLTZ_API_KEY:-${boltz_api_key:-}}"

if [[ -z "${BOLTZ_API_KEY}" ]]; then
  echo "boltz_cli_env: set Cloud secret boltz_api_key or export BOLTZ_API_KEY" >&2
  return 2 2>/dev/null || exit 2
fi

export BOLTZ_BASE_URL="${BOLTZ_BASE_URL:-https://api.boltz.bio}"

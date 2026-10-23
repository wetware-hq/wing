#!/usr/bin/env bash
# Map Cursor Cloud Agent / workspace secrets into Boltz API client env.
# Secret names (injected, never logged): boltz_api_key
# bindi / l1b_request_builder expect: BOLTZ_API_KEY (x-api-key header)
# Usage: source "$(dirname "$0")/boltz_cli_env.sh"

set -euo pipefail

export BOLTZ_API_KEY="${BOLTZ_API_KEY:-${boltz_api_key:-}}"

if [[ -z "${BOLTZ_API_KEY}" ]]; then
  echo "boltz_cli_env: set boltz_api_key (Cloud Agent secret) or BOLTZ_API_KEY" >&2
  return 2 2>/dev/null || exit 2
fi

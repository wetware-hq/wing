#!/usr/bin/env bash
# Map Cursor Cloud Agent / workspace secrets into Modal CLI env.
# Secret names (injected, never logged): modal_token_id, modal_token_secret
# Modal expects: MODAL_TOKEN_ID, MODAL_TOKEN_SECRET
# Usage: source "$(dirname "$0")/modal_cli_env.sh"

set -euo pipefail

export MODAL_TOKEN_ID="${MODAL_TOKEN_ID:-${modal_token_id:-}}"
export MODAL_TOKEN_SECRET="${MODAL_TOKEN_SECRET:-${modal_token_secret:-}}"

if [[ -z "${MODAL_TOKEN_ID}" || -z "${MODAL_TOKEN_SECRET}" ]]; then
  echo "modal_cli_env: set modal_token_id and modal_token_secret (Cloud Agent secrets) or MODAL_TOKEN_ID / MODAL_TOKEN_SECRET" >&2
  return 2 2>/dev/null || exit 2
fi

export PATH="${HOME}/.local/bin:${PATH}"

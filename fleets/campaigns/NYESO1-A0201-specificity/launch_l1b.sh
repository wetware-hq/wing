#!/usr/bin/env bash
# APPR-approved L1B fan-out to Boltz predict (hosted API).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=boltz_cli_env.sh
source "${ROOT}/boltz_cli_env.sh"

python3 "${ROOT}/l1b_submit.py" --submit "$@"

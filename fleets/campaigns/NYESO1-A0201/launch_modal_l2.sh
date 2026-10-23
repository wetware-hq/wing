#!/usr/bin/env bash
# Deploy and run cognate Layer-2 fan-out on Modal (CPU only). Requires APPR for spend policy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=modal_cli_env.sh
source "${ROOT}/modal_cli_env.sh"

ARTIFACTS="${1:-${ROOT}/run-one/artifacts}"
OUT="${2:-${ARTIFACTS}/layer2_results_modal.json}"

WHEEL="${ROOT}/dist/bindi-0.2.0-py3-none-any.whl"
if [[ ! -f "${WHEEL}" ]]; then
  echo "Build bindi wheel first (see modal_layer2_app.py header); expected ${WHEEL}" >&2
  exit 1
fi

cd "${ROOT}"
modal deploy modal_layer2_app.py
modal run modal_layer2_app.py::main --artifacts-dir "${ARTIFACTS}" --out-path "${OUT}"

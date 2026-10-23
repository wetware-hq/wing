#!/usr/bin/env bash
# NYESO1-A0201-specificity: L1B decoy refolds → Layer 2 → ranked panel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="${ROOT}/../NYESO1-A0201"
ARTIFACTS="${PARENT}/run-one/artifacts"

# shellcheck source=../NYESO1-A0201/boltz_cli_env.sh
source "${PARENT}/boltz_cli_env.sh"

cd "${ROOT}"

echo "=== L1B dry-run cost estimate ==="
python3 l1b_runner.py --dry-run

echo "=== L1B submit + mirror (decoys only; cognate from run-one) ==="
python3 l1b_runner.py --artifacts "${ARTIFACTS}" --workers 3 --approval "${APPROVAL:-NYESO1-A0201-specificity APPR launch 2026-10-23 (user LAUNCH)}"

echo "=== Layer 2 + Path A specificity panel ==="
cd "${PARENT}/run-one"
python3 layer2_orchestrator.py --specificity-campaign \
  --artifacts "${ARTIFACTS}" \
  --decoy-panel "${ROOT}/decoy_panel.yaml" \
  --panel-out "${ARTIFACTS}/panel.json"

echo "=== Path B ranked panel + transport T1 ==="
python3 "${ROOT}/specificity_orchestrator.py" \
  --artifacts "${ARTIFACTS}" \
  --ranked-out "${ROOT}/artifacts/ranked_panel.json" \
  --transport-out "${ROOT}/artifacts/transport_t1.json"

echo "DONE specificity campaign artifacts under ${ARTIFACTS} and ${ROOT}/artifacts/"

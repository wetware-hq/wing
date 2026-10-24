#!/usr/bin/env bash
# NYESO1-A0201-specificity: L1B decoy refolds → Layer 2 → ranked panel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="${ROOT}/../NYESO1-A0201"
ARTIFACTS="${PARENT}/run-one/artifacts"

# shellcheck source=../NYESO1-A0201/boltz_cli_env.sh
source "${PARENT}/boltz_cli_env.sh"

# Both scoring paths import bindi.ipsae. A bare `python3` that cannot import it
# does NOT fail the run: layer2_core records {"score_error": "ImportError ..."}
# and scoring continues with a null ipSAE descriptor, which ranks last for every
# row and so dilutes the margin instead of invalidating it. Resolve an
# interpreter that can actually import it, and refuse to start otherwise.
PYTHON="${PYTHON:-python3}"
if ! "${PYTHON}" -c "import bindi.ipsae" >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON} cannot import bindi.ipsae." >&2
  echo "  Both scoring paths need it, and without it they score a null" >&2
  echo "  descriptor silently rather than failing." >&2
  echo "  Set PYTHON to an interpreter with the bindi wheel installed, e.g." >&2
  echo "    PYTHON=/path/to/venv/bin/python $0" >&2
  exit 1
fi

# A launch submits paid predictions. The approval must name the run being
# approved now; a hardcoded default silently re-uses an approval nobody gave
# for this run, and goes stale the day after it is written.
if [[ -z "${APPROVAL:-}" ]]; then
  echo "ERROR: APPROVAL is not set." >&2
  echo "  This submits paid predictions. Pass the approval for THIS run, e.g." >&2
  echo "    APPROVAL='NYESO1-A0201-specificity APPR launch $(date +%F) (user LAUNCH)' $0" >&2
  exit 1
fi

cd "${ROOT}"

echo "=== L1B dry-run cost estimate ==="
"${PYTHON}" l1b_runner.py --dry-run

echo "=== L1B submit + mirror (decoys only; cognate from run-one) ==="
"${PYTHON}" l1b_runner.py --artifacts "${ARTIFACTS}" --workers 3 --approval "${APPROVAL}"

echo "=== Layer 2 + Path A specificity panel ==="
cd "${PARENT}/run-one"
"${PYTHON}" layer2_orchestrator.py --specificity-campaign \
  --artifacts "${ARTIFACTS}" \
  --decoy-panel "${ROOT}/decoy_panel.yaml" \
  --panel-out "${ARTIFACTS}/panel.json"

echo "=== Path B ranked panel + transport T1 ==="
# --score is required: without it the orchestrator finds no per-peptide artifact
# tree and writes a panel of incomplete margins, i.e. margins_computed=0.
"${PYTHON}" "${ROOT}/specificity_orchestrator.py" \
  --score \
  --artifacts "${ARTIFACTS}" \
  --ranked-out "${ROOT}/artifacts/ranked_panel.json" \
  --transport-out "${ROOT}/artifacts/transport_t1.json"

echo "DONE specificity campaign artifacts under ${ARTIFACTS} and ${ROOT}/artifacts/"

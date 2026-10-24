#!/usr/bin/env bash
# NYESO1-A0201-specificity: L1B decoy refolds → Layer 2 → ranked panel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="${ROOT}/../NYESO1-A0201"
# Overridable so a live resubmit can be written to a fresh tree instead of
# overwriting committed artifacts. Defaults are the historical paths.
ARTIFACTS="${ARTIFACTS:-${PARENT}/run-one/artifacts}"
OUT_DIR="${OUT_DIR:-${ROOT}/artifacts}"

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

# Skipping already-mirrored decoys is the default so a resumed run does not
# pay twice. SKIP_EXISTING=0 forces a real, paid resubmit of every job; the
# runner prints submitted= and skipped_existing= separately either way, so a
# replay of old artifacts can never be mistaken for a live submit.
SKIP_EXISTING="${SKIP_EXISTING:-1}"
SKIP_FLAG="--skip-existing"
if [[ "${SKIP_EXISTING}" == "0" ]]; then
  SKIP_FLAG="--no-skip-existing"
  echo "WARNING: SKIP_EXISTING=0 - every job will be resubmitted and PAID FOR," >&2
  echo "  including decoys already mirrored under ${ARTIFACTS}." >&2
fi

echo "=== L1B submit + mirror (decoys only; cognate from run-one) ==="
# --state-out follows OUT_DIR: the runner's own default writes state next to
# the campaign dir regardless of --artifacts, which would append a live run's
# records to the committed state log. OUT_DIR's default is that same path, so
# this changes nothing for a normal run.
"${PYTHON}" l1b_runner.py --artifacts "${ARTIFACTS}" --workers 3 \
  "${SKIP_FLAG}" --approval "${APPROVAL}" \
  --state-out "${OUT_DIR}/l1b_state.jsonl"

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
  --ranked-out "${OUT_DIR}/ranked_panel.json" \
  --transport-out "${OUT_DIR}/transport_t1.json"

echo "DONE specificity campaign artifacts under ${ARTIFACTS} and ${OUT_DIR}/"

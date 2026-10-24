"""Modal execution-host for NYESO1-A0201 LAYER 2 (pure-CPU interface scoring).

STATUS: LIVE. Deployed 2026-10-21 (Australia/Sydney) to Modal workspace `wetwarehq`
as app `nyeso1-a0201-layer2` (ap-gURujGEgW1B6kmE7RwKBfm); `score_one` has been
invoked remotely and returned. The build log confirms Modal pulled the pinned ghcr
BASE BY DIGEST (not by tag) and installed the bindi 0.2.0 wheel over 0.1.0 as an
additive layer. Deploying/registering a Function is not itself a run of layer 2;
the 10-design fan-out still sits downstream of the APPR approve edge.
Supersedes the earlier "NOTHING LIVE" status.

SCOPE (read infra.json "modal_scope_note" and FLEET.toml [platform.modal_layer2]):
  IN SCOPE  -> Modal as a CPU execution host for LAYER 2 (the ipSAE scoring worker
               that today runs in the pinned ghcr image on the box). Mathew's
               direction, 2026-10-21.
  REJECTED  -> self-hosting a GPU DESIGN model (BoltzGen/Boltz) on Modal GPU.
               That rejection (infra.json:406-411, :439, layer_1_boltz.self_hosting)
               STANDS. This file sets gpu NOTHING anywhere; it is CPU-only.

LAYER 1 (binder design on the Boltz HOSTED API, job prot_des_TY6KzyxULq8mACflXbhn)
is untouched and is NOT re-plumbed to Modal. This file never calls the Boltz design
endpoint.

GATING: iptm and plddt ONLY. ipsae / min_ipsae are RECORDED, NON-GATING
(FLEET.toml [descriptors], provenance). This worker emits them; it does not gate on them.

------------------------------------------------------------------------------
Modal APIs used, each with the doc URL fetched 2026-10-21 (Australia/Sydney):

  modal.Image.from_registry(tag, secret=...)
      https://modal.com/docs/reference/modal.Image      (from_registry)
      https://modal.com/docs/guide/images
      https://modal.com/docs/guide/custom-container-images  -> /guide/private-registries
      Private registry auth with static creds: the Secret must carry
      REGISTRY_USERNAME + REGISTRY_PASSWORD. (Docs state this verbatim for
      from_registry; ghcr.io is explicitly listed as a supported registry.)

  modal.Secret.from_name(name, required_keys=[...])
      https://modal.com/docs/reference/modal.Secret     (from_name)
      https://modal.com/docs/guide/secrets

  modal.App(...) / @app.function(...) / @app.local_entrypoint()
      https://modal.com/docs/reference/modal.App        (App, .function, .local_entrypoint)

  @app.function(cpu=, memory=, timeout=, retries=, env=,
                min_containers=, max_containers=, buffer_containers=,
                scaledown_window=)
      cpu/memory meaning + billing: https://modal.com/docs/guide/resources
      retries semantics:            https://modal.com/docs/guide/retries
      autoscaler knobs:             https://modal.com/docs/guide/scale
      input concurrency (REJECTED): https://modal.com/docs/guide/concurrent-inputs

  Function.starmap(...) for fan-out over the 10 designs
      https://modal.com/docs/reference/modal.Function   (starmap, map)

  modal.Volume (OPTIONAL, see note at bottom - deliberately NOT used)
      https://modal.com/docs/reference/modal.Volume
      https://modal.com/docs/guide/volumes
------------------------------------------------------------------------------

DEPLOY (when Mathew chooses to, under the APPR gate - do not run now):
  0. Auth: source modal_cli_env.sh (maps Cloud secrets modal_token_id / modal_token_secret
     to MODAL_TOKEN_ID / MODAL_TOKEN_SECRET), or run ./launch_modal_l2.sh.
  1. Create the ghcr read-only pull Secret on Modal (dashboard or CLI). ghcr package
     pulls need a GitHub token with `read:packages`:
         REGISTRY_USERNAME = <a GitHub username with read access to wetware-hq packages>
         REGISTRY_PASSWORD = <that token value>
     Name it exactly "ghcr-wetware-ro".
  2. `modal deploy modal_layer2_app.py`   (or `modal run ... ::main`)
  Both are spend events for layer 2 and MUST sit under spend_cap_usd and behind APPR
  (see the cost note at the bottom of this file).
"""

import json
import os
import pathlib

import modal

# -----------------------------------------------------------------------------
# DELIVERABLE 1 - the image.
# Pin the layer-2 env by its FULL ghcr digest. This digest is part of the fleet's
# content address (OD-8 first half, infra.json:256-257, :559) and MUST NOT be
# replaced by a tag. Using @sha256:... keeps the pull reproducible.
# -----------------------------------------------------------------------------
BINDI_FLEET_ENV_DIGEST = (
    "ghcr.io/wetware-hq/bindi-fleet-env"
    "@sha256:7e8762aebc3390611aafe0b67d925e567199d519e638113a80da33b86246a8e6"
)

# ghcr.io is PRIVATE -> static-credential auth via a Modal Secret holding
# REGISTRY_USERNAME + REGISTRY_PASSWORD (the GitHub PAT). See private-registries doc.
# NOTE on the content address (stated honestly, per the brief):
#   Modal pulls this base by digest and does NOT rebuild or mutate the base layers,
#   so the scientific environment (numpy==2.4.6, gemmi==0.7.5, shape-complementarity
#   ==0.2.0, biopython, ...) is byte-identical to the ghcr image. Modal then APPENDS
#   its own client-runtime layer on top, so the resulting *Modal* Image object id is
#   NOT the ghcr digest. The ghcr digest remains the pinned BASE and stays the content
#   address; only Modal's runtime layer is additive. No rebuild of the pinned layers
#   is required -> OD-8 is not reopened.
# REQUIREMENTS the base image must meet for from_registry (docs):
#   - built for linux/amd64
#   - `python` + `pip` on $PATH (the fleet-env image has them; it runs the worker)
#     -> so add_python is NOT needed and is intentionally omitted.
#   - an ENTRYPOINT that `exec "$@"` (or none). CONFIRMED 2026-10-21 by podman
#     inspect: the image has NO ENTRYPOINT (Cmd is only an import smoke test), so
#     no .entrypoint([...]) override is needed.
# THE PINNED IMAGE DOES NOT CONTAIN THE WORKER. Verified in-image 2026-10-21:
# `python -m bindi.ipsae` -> "No module named bindi.ipsae". The image ships bindi
# 0.1.0 with only cli, curate, generate, policy, resource, run; ipsae.py, gates.py,
# case.py, e2e.py, boltz.py and data.py are ALL absent. It was built 2026-10-20 from
# a tree predating the ipSAE work, so it is an ENVIRONMENT image, not a worker image.
# Fix: append the worker as a wheel layer. Do NOT rebuild and repin ghcr - that would
# reopen OD-8, invalidate the recorded digest everywhere, and buy nothing scientific,
# since this layer is pure python and touches no pinned scientific dependency.
# Build the wheel inside this same base image (verified: pip wheel --no-deps succeeds
# and the archive carries all six modules plus both data TOMLs):
#   podman run --rm -v <bindi>:/src -w /src <BINDI_FLEET_ENV_DIGEST> \
#     sh -lc 'pip wheel --no-deps --wheel-dir /src/dist /src'
# SECOND PINNED COORDINATE. With a wheel layer the ghcr digest pins the BASE, not the
# whole execution environment, so the worker MUST be pinned separately. Both are
# recorded in infra.json code_and_provenance.layer2_execution_pin:
WORKER_WHEEL = "bindi-0.2.0-py3-none-any.whl"
WORKER_WHEEL_SHA256 = (
    "6554960c1864ee3aabb64eccc7f639a78613daf2bb28b966abc27da1cb7d4e42"
)
WORKER_COMMIT = "70b6c6c"  # wetware-hq/bindi

# DEFECT D1 FIX (2026-10-21). The wheel is a BUILD ARTIFACT and is deliberately not
# committed, so its path has to be resolved, not assumed. A bare relative
# "dist/<wheel>" means "relative to the PROCESS CWD at deploy time" to Modal, not
# "beside this file" - so `modal deploy` worked only from a staging dir that happened
# to have dist/ beside the app copy, and failed from the repo. Resolve against
# __file__ instead, with an explicit env override for an out-of-tree build dir.
WHEEL_DIR = pathlib.Path(
    os.environ.get("BINDI_WHEEL_DIR") or (pathlib.Path(__file__).resolve().parent / "dist")
)
WHEEL_PATH = WHEEL_DIR / WORKER_WHEEL

# The guard is LOCAL-ONLY on purpose. Modal imports this module again INSIDE the
# container at runtime, where no local dist/ exists; an unguarded existence check
# would raise there and crash-loop every container. modal.is_local() is False in the
# container, so the check runs only at deploy time, which is the only time the local
# wheel is actually needed (add_local_file reads it during the image build).
if modal.is_local() and not WHEEL_PATH.is_file():
    raise SystemExit(
        f"worker wheel not found at {WHEEL_PATH}.\n"
        f"Build it inside the pinned base:\n"
        f"  podman run --rm -v <bindi>:/src -w /src {BINDI_FLEET_ENV_DIGEST} \\\n"
        f"    sh -lc 'pip wheel --no-deps --wheel-dir /src/dist /src'\n"
        f"and check sha256 == {WORKER_WHEEL_SHA256}\n"
        f"(or point BINDI_WHEEL_DIR at the directory holding it)."
    )

layer2_image = (
    modal.Image.from_registry(
        BINDI_FLEET_ENV_DIGEST,
        secret=modal.Secret.from_name(
            "ghcr-wetware-ro",
            required_keys=["REGISTRY_USERNAME", "REGISTRY_PASSWORD"],
        ),
    )
    # copy=True is required because a build step (run_commands) follows.
    .add_local_file(str(WHEEL_PATH), f"/tmp/{WORKER_WHEEL}", copy=True)
    .run_commands(f"pip install --no-cache-dir /tmp/{WORKER_WHEEL}")
)

app = modal.App("nyeso1-a0201-layer2")

# --chains is a STRICT ASSERTION against the CIF, not a repartitioning override:
# bindi._resolve_chain_specs requires every named chain to exist in the CIF with the
# EXACT residue count, and validate_token_alignment additionally requires the chain
# lengths to sum to the PAE token count. A hardcoded target-only string therefore
# CANNOT work: the predicted complex also contains the binder chain, whose length
# varies per design, so "A:275,B:99,C:9" always raises TokenAlignmentError.
# Default to "" -> the worker derives chains from the CIF, which is authoritative.
# Set CHAINS_ASSERTION per design only when the binder length is known, e.g.
# "A:275,B:99,C:9,D:62" for a 62-residue binder.
DEFAULT_CHAINS = ""

# Which chain is the designed binder. Required whenever the complex has >2 chains,
# because the worker emits one entry in pairs{} per chain PAIR (a 4-chain complex
# gives 6 pairs) and there is no single "the" interface to report without it.
BINDER_CHAIN = "D"

# The subtree l1b_runner.py:mirror_prediction_to_decoy_dir writes into, and the
# separator used to carry (design_id, decoy_id) through score_one's single id arg.
DECOY_REFOLDS_DIRNAME = "decoy_refolds"
COMPOSITE_ID_SEP = "::"


# -----------------------------------------------------------------------------
# DELIVERABLE 2 - the functions. CPU ONLY. gpu is NOT set anywhere.
#
# EVERY NUMBER BELOW IS MEASURED, NOT GUESSED. Measurements taken 2026-10-21 in the
# pinned image on the box, evidence /workspace/modal-deploy-2026-10-21/18,19,20:
#   * REALISTIC case - 445 tokens (target A:275,B:99,C:9 + a 62-residue binder D):
#       wall 0.58-0.64 s, peak RSS 55.4 MiB.
#   * 2x case - 890 tokens (binder D:507): wall 0.5835 s median, peak RSS 59.9 MiB.
#     i.e. NO measurable penalty at double the tokens; this is not an O(n^2) wall.
#   * Import alone (gemmi + numpy + biopython) is 0.478 s of that 0.58 s; a bare
#     interpreter is 0.016 s. So per-design COMPUTE is ~0.1 s and the run time is
#     dominated by interpreter startup + import, NOT by the linear algebra.
#   * Thread pinning - UNPINNED numpy spreads over 2.135 cores and burns
#     1.30-1.47 CPU-core-seconds per design for the SAME OR SLIGHTLY WORSE wall time
#     (0.6417 s median); pinned to 1 thread it uses 0.999 cores and 0.56-0.67
#     core-seconds at 0.5823 s median. Pinning roughly HALVES the bill and is
#     marginally FASTER. There is no tradeoff to make here.
#
# Docs checked 2026-10-21 (not memory): /guide/resources, /guide/retries,
# /guide/scale, /guide/concurrent-inputs.
#
#   cpu=1.0      ONE physical core. Measured: one pinned core matches 2.135 unpinned
#                cores on wall time (0.582 s vs 0.642 s), so extra cores buy nothing.
#                Billing is max(request, usage) (/guide/resources), so requesting
#                1.0 and using 0.999 wastes nothing; the 0.125 default would throttle
#                the gemmi parse for no saving, since usage would bill above it anyway.
#   memory=512   512 MiB. Measured peak RSS 55.4 MiB at 445 tokens and 59.9 MiB at
#                890 - so this is ~8.5x headroom, not a guess, and it is a REQUEST
#                (minimum), not a cap: no hard limit tuple is set, so a pathological
#                CIF is caught by `timeout`, not by an OOM kill. Memory is billed at
#                max(request, usage) too, and 0.5 GiB costs $0.0000011/s, i.e. 8% of
#                the CPU line. The 128 MiB default would be only ~2x the measured peak.
#   timeout=120  2 min, down from the earlier guessed 300. Real runs are 0.58 s, so
#                120 s is ~200x headroom: still a loud tripwire on a hang rather than
#                a tolerated one, and it halves the structural cost ceiling below.
#                Image pull / cold start is not charged against it (startup_timeout).
#   retries=0    Scoring is a PURE DETERMINISTIC function of (cif, pae). Every failure
#                here - TokenAlignmentError, a malformed CIF, absent pLDDT - recurs
#                identically, so an input retry only DELAYS the loud failure and can
#                mask the guard. Genuine infra flakes (container OOM / host loss) are
#                handled by Modal's container-crash rescheduling, which is orthogonal
#                to input retries (/guide/retries). So retries stays 0.
#   env={...}    BLAS/OpenMP thread pinning, the single biggest cost lever measured:
#                1.33-1.47 core-s unpinned vs 0.56-0.67 core-s pinned, for equal or
#                better latency. /guide/resources says Modal ALSO sets these based on
#                the cpu request - but that is Modal's heuristic, it is undocumented
#                what value it picks, and this worker runs the scorer in a SUBPROCESS.
#                Setting them explicitly makes the halving ours and auditable rather
#                than inherited. (Verified live post-deploy; see evidence 24.)
#
# CONCURRENCY - the one choice that actually matters, and it is NOT fan-out:
#   max_containers=2   NOT 10. A run is 10 designs x 0.58 s = ~6 s of real work. One
#                container per design would pay a cold start (image pull/sandbox
#                start, seconds) ten times to save ~5 s of wall. Per /guide/scale the
#                autoscaler spins containers up only when there is no capacity for
#                new inputs, and starmap queues inputs against the pool - so a SMALL
#                max_containers is exactly the "few containers, many inputs each,
#                sequentially" shape, with no extra knob needed. 2 rather than 1 keeps
#                a hung design from blocking the other nine.
#                HONEST CORRECTION to the import argument: container reuse does NOT
#                amortise the 0.478 s import, because score_one shells out to
#                `python -m bindi.ipsae` per design, so the import is paid per DESIGN
#                regardless of pool size. What a small pool saves is COLD STARTS. (The
#                import could be amortised by calling bindi in-process instead of via
#                subprocess - a real ~0.5 s/design saving, but a behaviour change to
#                the box-verified entrypoint and the TokenAlignmentError propagation,
#                so it is NOT done here. Flagged, not applied.)
#   min_containers=0   Scale to zero between runs. Layer 2 is a burst after ART, not
#                a service; a warm pool would bill idle containers for nothing.
#   buffer_containers=0  Same reason: no latency SLO to defend on a batch job.
#   scaledown_window=10  THE dominant cost term for a 6-second burst, which is why it
#                is set explicitly rather than left at the 60 s default: idle
#                containers are billed, so a 60 s tail x 2 containers = 120 billed
#                container-seconds against ~6 s of actual work - the idle tail would
#                cost 20x the compute. 10 s still lets a container serve the whole
#                queue without churn (inputs arrive <1 s apart).
#   @modal.concurrent  DELIBERATELY NOT USED. /guide/concurrent-inputs states
#                verbatim that for CPU-bound workloads input concurrency "will likely
#                not be as effective (or will even be counterproductive)". Two inputs
#                sharing one requested core would contend and halve each other's wall
#                time for zero throughput gain. (`max_inputs` is separately deprecated
#                in modal 1.6.2 in favour of single_use_containers, which is the exact
#                opposite of what is wanted here and is left False.)
#
# COST AT THIS CONFIGURATION (Modal list rates, read from `modal profile` billing
# 2026-10-21: CPU $0.0473/core/hour = $0.0000131/core/s; memory $0.008/GiB/hour =
# $0.00000222/GiB/s):
#   billed container-second = 1.0 core x $0.0000131 + 0.5 GiB x $0.00000222
#                           = $0.00001425 /s
#   PER DESIGN   0.58 s          -> $0.0000083   (0.0008 cents)
#   PER 10-DESIGN RUN: 5.8 s of work + 2 cold starts (~5 s each) + 2 x 10 s scaledown
#                   ~= 36 billed container-seconds -> ~$0.0005 (0.05 cents)
#     CONFIRMED LIVE 2026-10-21 (evidence 25): 10 inputs through starmap completed
#     in 6.77 s wall, served by EXACTLY 2 containers (not 10), every result carrying
#     thread_env pinned to 1. 2 x (6.8 s + 10 s scaledown) = 33.6 container-seconds
#     -> $0.00048. The estimate above is measured, not modelled.
#   HARD STRUCTURAL CEILING (billing = max(request,usage)):
#                   max_containers x timeout x $/s = 2 x 120 x $0.00001425 = $0.0034
#   The Starter plan includes $30/month of compute, so in practice this run is free;
#   it is still ADDED to the pre-APPR projection alongside the Boltz layer-1 spend and
#   checked against spend_cap_usd = 15.00. It is negligible, not zero.
# -----------------------------------------------------------------------------
class TokenAlignmentError(RuntimeError):
    """Local re-raise type mirroring bindi.ipsae's guard so the token/residue
    mismatch PROPAGATES out of Modal rather than being swallowed."""


# Measured thread pinning: 1.33-1.47 core-s unpinned -> 0.56-0.67 core-s pinned,
# at equal-or-better wall time (evidence 18 sections A vs B). Set on the FUNCTION
# (env=), not on the image, so no image layer is added and the pinned base build is
# untouched; subprocesses inherit the container environment.
BLAS_SINGLE_THREAD = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


@app.function(
    image=layer2_image,
    env=BLAS_SINGLE_THREAD,
    cpu=1.0,
    memory=512,
    timeout=120,
    retries=0,
    min_containers=0,
    max_containers=2,
    buffer_containers=0,
    scaledown_window=10,
)
def score_one(
    design_id: str,
    cif_bytes: bytes,
    pae_bytes: bytes,
    chains: str = DEFAULT_CHAINS,
    binder_chain: str = BINDER_CHAIN,
) -> dict:
    """Score ONE design in-image via the worker's documented, box-verified entrypoint:
        python -m bindi.ipsae <pae.npz> <_predicted.cif> [--chains A:275,B:99,C:9]
    (infra.json:123; implements dunbracklab/IPSAE ipsae_d0res, bindi takes
    min(A->B, B->A) for the conservative weakest-direction screen, infra.json:126).

    Returns the NON-GATING descriptors: ipsae, min_ipsae (both chain orderings when
    the worker reports them), complex_plddt, and plddt.present. The token-alignment
    guard is preserved: a TokenAlignmentError raised in-image is re-raised here, never
    swallowed.

    CONTRACT NOTE (honest): the exact stdout schema of `python -m bindi.ipsae` is
    defined in the bindi repo, NOT in wing, and is not in this clone. This reader
    expects the worker to emit a JSON object on stdout and maps its keys below. If
    bindi instead writes a metrics file, point `_read_worker_output` at that file.
    The key assertions below FAIL LOUDLY if the schema does not match, surfacing the
    bindi<->wing contract mismatch rather than returning partial data.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        cif_path = d / f"{design_id}_predicted.cif"
        pae_path = d / f"{design_id}_pae.npz"
        cif_path.write_bytes(cif_bytes)
        pae_path.write_bytes(pae_bytes)

        cmd = ["python", "-m", "bindi.ipsae", str(pae_path), str(cif_path)]
        if chains:
            cmd += ["--chains", chains]

        proc = subprocess.run(cmd, capture_output=True, text=True)

        # --- preserve the guard: do NOT swallow TokenAlignmentError ---
        combined = (proc.stderr or "") + (proc.stdout or "")
        if "TokenAlignmentError" in combined:
            raise TokenAlignmentError(
                f"[{design_id}] bindi.ipsae raised TokenAlignmentError:\n{proc.stderr}"
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"[{design_id}] bindi.ipsae exited {proc.returncode}:\n{proc.stderr}"
            )

        raw = _read_worker_output(proc.stdout)

    # The worker's JSON is NESTED (verified live in-image 2026-10-21):
    #   {chains:[{chain_id,length}], n_tokens, ordered:{"A->B":..,"B->A":..},
    #    pae_cutoff,
    #    pairs:{"A|B":{ipsae_A_to_B, ipsae_B_to_A, min_ipsae}},
    #    plddt:{complex_plddt, interface_plddt, present}}
    # There are NO top-level "ipsae"/"min_ipsae"/"complex_plddt" keys.
    pair_key, pair = _select_pair(raw, binder_chain)
    chain_a, chain_b = pair_key.split("|")
    plddt = raw["plddt"]
    result = {
        "design_id": design_id,
        "pair": pair_key,
        # NON-GATING, recorded only. "ipsae" is the conservative weakest-direction
        # screen, i.e. min(A->B, B->A), which is exactly pairs[key]["min_ipsae"].
        "ipsae": pair["min_ipsae"],
        "min_ipsae": pair["min_ipsae"],
        # both chain orderings, keyed by the ACTUAL chain ids in this pair:
        "ipsae_ab": pair[f"ipsae_{chain_a}_to_{chain_b}"],
        "ipsae_ba": pair[f"ipsae_{chain_b}_to_{chain_a}"],
        "complex_plddt": plddt["complex_plddt"],
        "interface_plddt": plddt["interface_plddt"],
        "plddt_present": bool(plddt["present"]),
        "n_tokens": raw["n_tokens"],
        "chains_reported": raw["chains"],
        "chains_asserted": chains or None,
        # PROVENANCE: record the thread pinning that was ACTUALLY in force for this
        # score, rather than asserting it in a comment. Measured unpinned cost is
        # ~2.4x pinned (evidence 18), so a silently-unpinned container is a cost
        # regression that would otherwise be invisible in the results file.
        "thread_env": {k: os.environ.get(k) for k in sorted(BLAS_SINGLE_THREAD)},
        "worker_raw": raw,  # full output kept for provenance / replay
    }
    return result


def _select_pair(raw: dict, binder_chain: str | None) -> tuple[str, dict]:
    """Resolve the worker's pairs{} map to the ONE interface this design is judged on.

    A 2-chain complex has exactly one pair and needs no hint. A real campaign complex
    (target A/B/C + binder D) has 6 pairs, so the binder chain must be named; we then
    take the WEAKEST binder-containing interface, consistent with bindi's conservative
    min(A->B, B->A) screen. Failing loudly beats silently scoring the wrong interface.
    """
    pairs = raw["pairs"]
    if not binder_chain:
        if len(pairs) != 1:
            raise RuntimeError(
                f"binder_chain is not set and the complex has {len(pairs)} chain pairs "
                f"({sorted(pairs)}); cannot infer which interface to score"
            )
        return next(iter(pairs.items()))
    candidates = {k: v for k, v in pairs.items() if binder_chain in k.split("|")}
    if not candidates:
        raise RuntimeError(
            f"binder chain {binder_chain!r} is not in any reported pair ({sorted(pairs)}); "
            f"chains present: {[c['chain_id'] for c in raw['chains']]}"
        )
    return min(candidates.items(), key=lambda kv: kv[1]["min_ipsae"])


def _read_worker_output(stdout: str) -> dict:
    """Parse the worker's stdout as JSON.

    CONFIRMED 2026-10-21 against bindi @70b6c6c installed into the pinned image:
    `python -m bindi.ipsae` writes ONE JSON object to stdout via
    json.dump(result, sys.stdout, indent=2, sort_keys=True). It does not write a
    metrics file, so parsing stdout is correct."""
    stdout = (stdout or "").strip()
    if not stdout:
        raise RuntimeError("bindi.ipsae produced no stdout to parse")
    return json.loads(stdout)


# -----------------------------------------------------------------------------
# Fan-out + deterministic write-back entrypoint.
# Reads a local artifact dir of the 10 designs, scores them on Modal via starmap,
# and writes ONE canonical-JSON results file (sort_keys + compact separators, the
# fleet's canonical-JSON hashing rule), sorted by design_id so the output - and thus
# its hash - is deterministic regardless of completion order.
#
# local_entrypoint + starmap docs:
#   https://modal.com/docs/reference/modal.App       (local_entrypoint)
#   https://modal.com/docs/reference/modal.Function  (starmap)
# -----------------------------------------------------------------------------
@app.local_entrypoint()
def main(
    artifacts_dir: str = "run-one/artifacts",
    out_path: str = "run-one/layer2_results.json",
    chains: str = DEFAULT_CHAINS,
    binder_chain: str = BINDER_CHAIN,
    mode: str = "cognate",
):
    """Score an artifact tree on Modal via starmap.

    mode="cognate" (DEFAULT, unchanged behaviour): expects
    artifacts_dir/<design_id>/ each holding `_predicted.cif` and `pae.npz` (the ART
    node outputs, infra.json:100-102). 10 inputs for this campaign. Mirror those
    off-API first (7-day retention clock) before running this.

    mode="decoys": expects artifacts_dir/decoy_refolds/<design_id>/<decoy_id>/, the
    layout l1b_runner.py:mirror_prediction_to_decoy_dir actually writes. 100 inputs
    for this campaign (10 designs x 10 decoys). Same chain layout as the cognate -
    verified on the run-one tree, A:275,B:99,C:9,D:73 for both - so DEFAULT_CHAINS
    ("", i.e. let the worker read the chains off the mmCIF) is correct for both modes
    and no per-mode chain override is needed.

    WHY A MODE FLAG AND NOT A REPLACEMENT: the cognate path is the one that produced
    run-one/artifacts/layer2_results_modal.json under run ap-IshjN3qkaWX2kvCezJbqeM.
    Keeping it byte-reproducible matters more than tidiness, so decoys are additive.

    score_one takes a single `design_id` string, so decoy inputs pass the composite
    "<design_id>::<decoy_id>". It is split back into separate design_id/decoy_id keys
    below, so a caller never has to parse the composite out of the results file.
    """
    adir = pathlib.Path(artifacts_dir)
    if mode not in ("cognate", "decoys"):
        raise SystemExit(f"mode must be 'cognate' or 'decoys', got {mode!r}")

    inputs = []
    if mode == "cognate":
        designs = sorted(p.name for p in adir.iterdir() if p.is_dir())
        # decoy_refolds/ is a sibling of the per-design dirs, not one of them.
        designs = [d for d in designs if d != DECOY_REFOLDS_DIRNAME]
        if not designs:
            raise SystemExit(f"no design subdirs under {adir}")
        for did in designs:
            cif = next(adir.joinpath(did).glob("*_predicted.cif"))
            pae = next(adir.joinpath(did).glob("*pae*.npz"))
            inputs.append((did, cif.read_bytes(), pae.read_bytes(), chains, binder_chain))
    else:
        root = adir / DECOY_REFOLDS_DIRNAME
        if not root.is_dir():
            raise SystemExit(f"no {DECOY_REFOLDS_DIRNAME}/ tree under {adir}")
        for design_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for decoy_dir in sorted(p for p in design_dir.iterdir() if p.is_dir()):
                cif = next(decoy_dir.glob("*_predicted.cif"))
                pae = next(decoy_dir.glob("*pae*.npz"))
                inputs.append((
                    f"{design_dir.name}{COMPOSITE_ID_SEP}{decoy_dir.name}",
                    cif.read_bytes(),
                    pae.read_bytes(),
                    chains,
                    binder_chain,
                ))
        if not inputs:
            raise SystemExit(f"no decoy leaf dirs with a *_predicted.cif under {root}")

    print(f"mode={mode}: {len(inputs)} input(s) enumerated under {adir}")

    # starmap: each tuple is unpacked into score_one's positional args.
    # order_outputs=True (default) -> outputs match input order; we also sort below.
    results = list(score_one.starmap(inputs))

    if mode == "decoys":
        # Split the composite back into its two identity fields. Done here rather than
        # in score_one so the remote function keeps its single-id signature and the
        # cognate path is untouched.
        for r in results:
            composite = r["design_id"]
            design_id, _, decoy_id = composite.partition(COMPOSITE_ID_SEP)
            r["design_id"] = design_id
            r["decoy_id"] = decoy_id
        results.sort(key=lambda r: (r["design_id"], r["decoy_id"]))
    else:
        results.sort(key=lambda r: r["design_id"])

    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "campaign": "NYESO1-A0201",
                "layer": 2,
                "mode": mode,
                "n": len(results),
                "results": results,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"wrote {len(results)} layer-2 results ({mode}) -> {out}")


# -----------------------------------------------------------------------------
# COST SURFACE and how it sits UNDER spend_cap_usd=15.00 and the APPR gate.
#
#   Where it sits in the graph: L2 is downstream of the APPR approve edge
#   (CFG -> APPR -> L1A -> L1B -> ART -> L2, FLEET.toml [graph].edges). So this work
#   only runs on the approve path - it ALREADY inherits the human gate. No new gate.
#
#   The $ ceiling is bounded structurally (billing = max(request, usage), per the
#   resources doc): billable container-seconds <= max_containers * timeout
#   = 2 * 120 = 240, at 1.0 core + 0.5 GiB = $0.00001425/s -> $0.0034 HARD CEILING
#   for a 10-design run. MEASURED expectation is ~36 container-seconds -> ~$0.0005.
#   Rates read from `modal profile` billing 2026-10-21: CPU $0.0473/core/hour,
#   memory $0.008/GiB/hour. The Starter plan includes $30/month of compute, so in
#   practice this is free; spend to date on this app at deploy time was $0.06
#   metered, fully covered by credits, $0.00 billed.
#
#   Therefore the rule (do not hand-wave): the Modal layer-2 projection must be ADDED
#   to spent_to_date_usd and included in the SAME pre-APPR cost projection as the
#   Boltz spend; the run aborts if (Boltz + Modal projected) > spend_cap_usd. Modal
#   is CPU-only here, so there is no GPU spend surface at all.
#
# OPTIONAL COMPLEXITY DELIBERATELY CUT (min idiot index):
#   A modal.Volume (https://modal.com/docs/reference/modal.Volume) could persist the
#   artifacts/results on Modal. It is NOT used: the 10 artifacts are tiny and are
#   already mirrored to the repo/box off-API, so a Volume adds a durability surface
#   that buys nothing here. Add one only if Modal-side durable mirroring is wanted;
#   the import + from_name("...", create_if_missing=True) pattern is in the docs.
# -----------------------------------------------------------------------------

"""Modal execution-host for NYESO1-A0201 LAYER 2 (pure-CPU interface scoring).

STATUS: specification + ready-to-deploy code. NOTHING LIVE. This module has NOT
been `modal deploy`-ed or `modal run`-done; no Modal account/token was created or
used. MODAL_TOKEN_ID / MODAL_TOKEN_SECRET stay inert (infra.json:452-453).

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

  @app.function(cpu=, memory=, timeout=, retries=, max_containers=)
      cpu/memory meaning + billing: https://modal.com/docs/guide/resources
      retries semantics:            https://modal.com/docs/guide/retries

  Function.starmap(...) for fan-out over the 10 designs
      https://modal.com/docs/reference/modal.Function   (starmap, map)

  modal.Volume (OPTIONAL, see note at bottom - deliberately NOT used)
      https://modal.com/docs/reference/modal.Volume
      https://modal.com/docs/guide/volumes
------------------------------------------------------------------------------

DEPLOY (when Mathew chooses to, under the APPR gate - do not run now):
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

layer2_image = (
    modal.Image.from_registry(
        BINDI_FLEET_ENV_DIGEST,
        secret=modal.Secret.from_name(
            "ghcr-wetware-ro",
            required_keys=["REGISTRY_USERNAME", "REGISTRY_PASSWORD"],
        ),
    )
    # copy=True is required because a build step (run_commands) follows.
    .add_local_file(f"dist/{WORKER_WHEEL}", f"/tmp/{WORKER_WHEEL}", copy=True)
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


# -----------------------------------------------------------------------------
# DELIVERABLE 2 - the functions. CPU ONLY. gpu is NOT set anywhere.
#
# Resource choices (every number justified; docs: /guide/resources, /guide/retries):
#   cpu=1.0      One physical core. ipSAE is O(n^2) numpy over a ~256x256 PAE plus a
#                single gemmi CIF parse: sub-second to low-seconds, single-threaded.
#                More cores buy nothing (min engineering idiot index). 1.0 guarantees
#                a full core so the gemmi parse is not throttled under the 0.125 default.
#   memory=2048  2 GiB. The arrays are tiny (256x256 float32 ~= 0.26 MiB); the real
#                footprint is importing numpy+scipy+gemmi+biopython. 2 GiB is generous
#                headroom with an OOM-kill backstop if a pathological CIF blows up;
#                the default 128 MiB would risk OOM on import alone.
#   timeout=300  5 min. A single design scores in seconds; 300 s is a loud upper bound
#                that trips on a hang (e.g. a pathological CIF) rather than tolerating
#                it. Image pull/cold start is NOT counted against this.
#   retries=0    Scoring is a PURE DETERMINISTIC function of (cif, pae). Every failure
#                here - TokenAlignmentError, a malformed CIF, absent pLDDT - is
#                deterministic and would recur identically, so an input-retry buys
#                nothing and would only DELAY the loud failure (and could mask the
#                guard). Genuine infra flakes (container OOM/host loss) are handled
#                separately by Modal's container-crash rescheduling, which is
#                orthogonal to input retries (retries guide). So retries stays 0.
#   max_containers=10  A run is exactly 10 designs; cap concurrency at 10 so the burst
#                (and thus the billable-core-second burst) is bounded to one container
#                per design and never oversubscribes.
# -----------------------------------------------------------------------------
class TokenAlignmentError(RuntimeError):
    """Local re-raise type mirroring bindi.ipsae's guard so the token/residue
    mismatch PROPAGATES out of Modal rather than being swallowed."""


@app.function(
    image=layer2_image,
    cpu=1.0,
    memory=2048,
    timeout=300,
    retries=0,
    max_containers=10,
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
):
    """Expect artifacts_dir/<design_id>/ each holding `_predicted.cif` and `pae.npz`
    (the ART node outputs, infra.json:100-102). Mirror those off-API first (7-day
    retention clock) before running this."""
    adir = pathlib.Path(artifacts_dir)
    designs = sorted(p.name for p in adir.iterdir() if p.is_dir())
    if not designs:
        raise SystemExit(f"no design subdirs under {adir}")

    inputs = []
    for did in designs:
        cif = next(adir.joinpath(did).glob("*_predicted.cif"))
        pae = next(adir.joinpath(did).glob("*pae*.npz"))
        inputs.append((did, cif.read_bytes(), pae.read_bytes(), chains, binder_chain))

    # starmap: each tuple is unpacked into score_one's positional args.
    # order_outputs=True (default) -> outputs match input order; we also sort below.
    results = list(score_one.starmap(inputs))
    results.sort(key=lambda r: r["design_id"])

    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"campaign": "NYESO1-A0201", "layer": 2, "n": len(results), "results": results},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    print(f"wrote {len(results)} layer-2 results -> {out}")


# -----------------------------------------------------------------------------
# COST SURFACE and how it sits UNDER spend_cap_usd=15.00 and the APPR gate.
#
#   Where it sits in the graph: L2 is downstream of the APPR approve edge
#   (CFG -> APPR -> L1A -> L1B -> ART -> L2, FLEET.toml [graph].edges). So this work
#   only runs on the approve path - it ALREADY inherits the human gate. No new gate.
#
#   The $ ceiling is bounded structurally (billing = max(request, usage), per the
#   resources doc): billable core-seconds <= max_containers * timeout * cpu
#   = 10 * 300 * 1.0 = 3000 core-seconds HARD CEILING for a 10-design run; memory is
#   billed at max(request,usage) alongside. Real usage is far below (seconds/design).
#   The exact $/core-second is on Modal's pricing page (NOT fetched this session, so
#   not quoted here); at that rate 3000 core-s of CPU is cents, negligible beside the
#   $15 Boltz layer-1 spend - but it is NOT zero.
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

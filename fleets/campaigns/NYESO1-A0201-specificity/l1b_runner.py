#!/usr/bin/env python3
"""Submit L1B decoy refolds (Boltz structure-and-binding), mirror artifacts, resume-safe."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from l1b_request_builder import build_structure_and_binding_payload, load_yaml_minimal

API_BASE = "https://api.boltz.bio/compute/v1/predictions/structure-and-binding"
DEFAULT_APPROVAL = "NYESO1-A0201-specificity APPR launch 2026-10-23 (user LAUNCH)"


# Descriptors that FLEET.toml gates on. A mirrored decoy missing one of these
# is not a usable decoy, however well-formed its archive is.
GATED_METRIC_KEYS = ("iptm", "complex_plddt")


class BoltzPredictError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("BOLTZ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("BOLTZ_API_KEY not set; source ../NYESO1-A0201/boltz_cli_env.sh")
    return key


def _call(method: str, path: str, body: dict[str, Any] | None = None, *, timeout: float = 120) -> Any:
    url = API_BASE + path
    headers = {"x-api-key": _api_key(), "accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, sort_keys=True).encode()
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode()
            return json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise BoltzPredictError(f"HTTP {exc.code} {path}: {detail[:500]}") from None


def estimate_cost(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("POST", "/estimate-cost", payload)


def submit(payload: dict[str, Any], *, approval: str) -> str:
    if not approval.strip():
        raise BoltzPredictError("submit requires non-empty --approval (APPR gate)")
    resp = _call("POST", "", payload)
    pid = resp.get("id")
    if not pid:
        raise BoltzPredictError(f"submit returned no id: {json.dumps(resp)[:300]}")
    return str(pid)


def retrieve(prediction_id: str) -> dict[str, Any]:
    return _call("GET", f"/{prediction_id}")


def wait_succeeded(prediction_id: str, *, poll_s: float = 8, timeout_s: float = 900) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        doc = retrieve(prediction_id)
        status = doc.get("status")
        if status == "succeeded":
            return doc
        if status == "failed":
            raise BoltzPredictError(f"{prediction_id} failed: {doc.get('error')}")
        time.sleep(poll_s)
    raise BoltzPredictError(f"{prediction_id} timed out after {timeout_s}s")


def _download_url(url: str, *, timeout: float = 180) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def mirror_prediction_to_decoy_dir(doc: dict[str, Any], dest: Path, *, decoy_id: str) -> None:
    """Extract archive into decoy_refolds/<design>/<decoy_id>/ with layer-2 naming."""
    dest.mkdir(parents=True, exist_ok=True)
    output = doc.get("output") or {}
    archive = output.get("archive") or {}
    url = archive.get("url")
    if not url:
        raise BoltzPredictError("succeeded prediction missing archive.url")
    raw = _download_url(url)
    cif_bytes = pae_bytes = metrics_bytes = None
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
        for member in tf.getmembers():
            f = tf.extractfile(member)
            if f is None:
                continue
            data = f.read()
            if member.name.endswith("metrics.json"):
                metrics_bytes = data
            elif member.name.endswith(".cif"):
                cif_bytes = data
            elif member.name.endswith("pae.npz"):
                pae_bytes = data
    if not cif_bytes or not pae_bytes or not metrics_bytes:
        raise BoltzPredictError(f"archive missing cif/pae/metrics members for {decoy_id}")
    cif_out = dest / f"{decoy_id}_predicted.cif"
    pae_out = dest / "pae.npz"
    metrics_out = dest / "metrics.json"
    cif_out.write_bytes(cif_bytes)
    pae_out.write_bytes(pae_bytes)
    metrics = json.loads(metrics_bytes.decode())
    best = (output.get("best_sample") or {}).get("metrics") or {}
    merged = {**metrics, **best}
    binding = output.get("binding_metrics") or {}
    if binding.get("binding_confidence") is not None:
        merged["binding_confidence"] = binding["binding_confidence"]
    if "iptm" not in merged and best.get("iptm") is not None:
        merged["iptm"] = best["iptm"]
    # The merge was written with no check that the gated descriptors survived
    # it. A decoy whose metrics.json lacks iptm was still recorded as
    # "mirrored" and counted as OK, and the missing value then ranked last
    # everywhere downstream rather than stopping the run.
    missing_gated = [k for k in GATED_METRIC_KEYS if merged.get(k) is None]
    if missing_gated:
        raise BoltzPredictError(
            f"{decoy_id}: prediction output has no {', '.join(missing_gated)}; "
            "these feed the gated descriptors, so the decoy cannot be mirrored "
            "as complete"
        )
    metrics_out.write_text(json.dumps(merged, indent=2, sort_keys=True))
    meta = {
        "prediction_id": doc.get("id"),
        "model": doc.get("model"),
        "campaign": "NYESO1-A0201-specificity",
        "decoy_id": decoy_id,
    }
    (dest / "l1b_run.json").write_text(json.dumps(meta, indent=2, sort_keys=True))


def load_jobs(campaign_dir: Path, *, decoys_only: bool = True) -> list[dict[str, Any]]:
    survivors = load_yaml_minimal(campaign_dir / "survivor_panel.yaml")["survivors"]
    decoy_doc = load_yaml_minimal(campaign_dir / "decoy_panel.yaml")
    peptides: list[dict[str, Any]] = []
    if not decoys_only:
        peptides.append(
            {
                "peptide_id": decoy_doc["cognate"]["peptide_id"],
                "sequence": decoy_doc["cognate"]["sequence"],
            }
        )
    for m in decoy_doc.get("mutants", []):
        peptides.append({"peptide_id": m["id"], "sequence": m["sequence"]})
    jobs: list[dict[str, Any]] = []
    for s in survivors:
        for p in peptides:
            payload = build_structure_and_binding_payload(
                binder_sequence=s["binder_sequence"],
                peptide_sequence=p["sequence"],
            )
            jobs.append(
                {
                    "design_id": s["design_id"],
                    "decoy_id": p["peptide_id"],
                    "payload": payload,
                }
            )
    return jobs


def run_one_job(
    job: dict[str, Any],
    artifacts_root: Path,
    *,
    approval: str,
    dry_run: bool,
    skip_existing: bool,
) -> dict[str, Any]:
    design_id = job["design_id"]
    decoy_id = job["decoy_id"]
    dest = artifacts_root / "decoy_refolds" / design_id / decoy_id
    if skip_existing and (dest / "pae.npz").is_file() and list(dest.glob("*_predicted.cif")):
        return {"design_id": design_id, "decoy_id": decoy_id, "status": "skipped_existing"}
    if dry_run:
        est = estimate_cost(job["payload"])
        return {
            "design_id": design_id,
            "decoy_id": decoy_id,
            "status": "dry_run",
            "estimated_cost_usd": est.get("estimated_cost_usd"),
        }
    pid = submit(job["payload"], approval=approval)
    doc = wait_succeeded(pid)
    mirror_prediction_to_decoy_dir(doc, dest, decoy_id=decoy_id)
    return {
        "design_id": design_id,
        "decoy_id": decoy_id,
        "status": "mirrored",
        "prediction_id": pid,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="L1B decoy refold runner (Boltz predictions API)")
    ap.add_argument("--campaign-dir", default=str(Path(__file__).resolve().parent))
    ap.add_argument(
        "--artifacts",
        default=str(Path(__file__).resolve().parent.parent / "NYESO1-A0201" / "run-one" / "artifacts"),
    )
    ap.add_argument("--approval", default=DEFAULT_APPROVAL)
    ap.add_argument("--dry-run", action="store_true", help="estimate-cost only, no submit")
    ap.add_argument("--limit", type=int, default=0, help="max jobs (0 = all)")
    ap.add_argument("--workers", type=int, default=3, help="concurrent predictions")
    # `action="store_true", default=True` made this impossible to turn off:
    # there was no --no-skip-existing, so once a decoy had been mirrored the
    # paid submit branch was unreachable and a "launch" silently re-reported
    # old artifacts as a successful run. Skipping stays the default so a rerun
    # resumes from state instead of paying twice, but it is now switchable.
    ap.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="skip decoys already mirrored on disk (default); "
        "--no-skip-existing forces a real, paid resubmit of every job",
    )
    ap.add_argument("--state-out", default=None, help="JSONL progress log")
    args = ap.parse_args(argv)

    campaign_dir = Path(args.campaign_dir)
    artifacts_root = Path(args.artifacts)
    jobs = load_jobs(campaign_dir, decoys_only=True)
    if args.limit:
        jobs = jobs[: args.limit]

    if args.dry_run:
        sample = estimate_cost(jobs[0]["payload"])
        # A hardcoded 0.05 substituted for a missing price printed invented
        # money in the same format as a real estimate.
        if sample.get("estimated_cost_usd") is None:
            raise SystemExit(
                "cost estimate unavailable: the API response has no "
                "estimated_cost_usd, and a guessed unit price is not an estimate"
            )
        unit = float(sample["estimated_cost_usd"])
        print(
            json.dumps(
                {
                    "jobs": len(jobs),
                    "estimated_total_usd": round(unit * len(jobs), 4),
                    "per_job_sample": sample,
                },
                indent=2,
            )
        )
        return 0

    state_path = Path(args.state_out or campaign_dir / "artifacts" / "l1b_state.jsonl")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    workers = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                run_one_job,
                job,
                artifacts_root,
                approval=args.approval,
                dry_run=False,
                skip_existing=args.skip_existing,
            ): job
            for job in jobs
        }
        for fut in as_completed(futs):
            rec = fut.result()
            results.append(rec)
            with state_path.open("a") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
            print(json.dumps(rec, sort_keys=True))

    submitted = sum(1 for r in results if r["status"] == "mirrored")
    skipped = sum(1 for r in results if r["status"] == "skipped_existing")
    ok = submitted + skipped
    # `ok=100` counted a run that submitted nothing exactly like one that
    # submitted everything, so a reader could not tell a real launch from a
    # replay of old artifacts. Report the two separately, and say loudly when
    # nothing was actually submitted.
    print(
        f"DONE jobs={len(jobs)} submitted={submitted} skipped_existing={skipped} "
        f"ok={ok} state={state_path}"
    )
    if jobs and submitted == 0:
        print(
            "NOTE: no prediction was submitted; every job was skipped as already "
            "mirrored on disk, so this run cost nothing and produced no new data. "
            "Pass --no-skip-existing to force a real (paid) resubmit.",
            file=sys.stderr,
        )
    return 0 if ok == len(jobs) else 1


if __name__ == "__main__":
    raise SystemExit(main())

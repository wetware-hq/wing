#!/usr/bin/env python3
"""Submit L1B decoy refolds to Boltz hosted predict API (APPR-gated spend)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

CAMPAIGN_DIR = Path(__file__).resolve().parent
RUN_ONE_ART = CAMPAIGN_DIR.parent / "NYESO1-A0201" / "run-one" / "artifacts"

sys.path.insert(0, str(CAMPAIGN_DIR))
from l1b_request_builder import build_predict_request, write_l1b_manifest  # noqa: E402
from specificity_orchestrator import decoy_peptide_entries  # noqa: E402


def _load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text())


def _api_key() -> str:
    key = os.environ.get("BOLTZ_API_KEY") or os.environ.get("boltz_api_key")
    if not key:
        raise SystemExit("BOLTZ_API_KEY / boltz_api_key not set (source boltz_cli_env.sh)")
    return key


def _prepare_input(request: dict) -> dict:
    body = {k: v for k, v in request.items() if k != "_meta"}
    inp = dict(body.get("input") or {})
    inp.setdefault(
        "binding",
        {"type": "protein_protein_binding", "binder_chain_ids": ["D"]},
    )
    return inp


def _peptides(decoy_doc: dict) -> list[dict]:
    cognate = dict(decoy_doc["cognate"])
    entries = [cognate]
    for m in decoy_peptide_entries(decoy_doc):
        pid = m.get("peptide_id") or m.get("id")
        entries.append({"peptide_id": pid, "sequence": m["sequence"]})
    return entries


def build_jobs(survivors_path: Path, decoy_path: Path) -> list[dict]:
    survivors_doc = _load_yaml(survivors_path)
    decoy_doc = _load_yaml(decoy_path)
    peptides = _peptides(decoy_doc)
    jobs: list[dict] = []
    for s in survivors_doc["survivors"]:
        for p in peptides:
            req = build_predict_request(
                binder_sequence=s["binder_sequence"],
                peptide_sequence=p["sequence"],
            )
            jobs.append(
                {
                    "design_id": s["design_id"],
                    "peptide_id": p["peptide_id"],
                    "request": req,
                }
            )
    return jobs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="L1B Boltz predict submit")
    ap.add_argument("--survivors", default=str(CAMPAIGN_DIR / "survivor_panel.yaml"))
    ap.add_argument("--decoys", default=str(CAMPAIGN_DIR / "decoy_panel.yaml"))
    ap.add_argument(
        "--manifest-out",
        default=str(CAMPAIGN_DIR / "artifacts" / "l1b_manifest.json"),
    )
    ap.add_argument(
        "--jobs-out",
        default=str(CAMPAIGN_DIR / "artifacts" / "l1b_jobs.json"),
    )
    ap.add_argument("--dry-run", action="store_true", help="Estimate cost on first job only")
    ap.add_argument("--submit", action="store_true", help="POST all jobs (start, no wait)")
    ap.add_argument("--limit", type=int, default=0, help="Max jobs to submit (0 = all)")
    ap.add_argument("--sleep", type=float, default=0.25, help="Seconds between submits")
    args = ap.parse_args(argv)

    jobs = build_jobs(Path(args.survivors), Path(args.decoys))
    if args.limit:
        jobs = jobs[: args.limit]

    manifest_path = Path(args.manifest_out)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    survivors_doc = _load_yaml(Path(args.survivors))
    decoy_doc = _load_yaml(Path(args.decoys))
    write_l1b_manifest(survivors_doc["survivors"], _peptides(decoy_doc), manifest_path)
    print(f"WROTE {manifest_path} ({len(jobs)} jobs)")

    if not args.dry_run and not args.submit:
        print("Use --dry-run or --submit")
        return 0

    from boltz_api import Boltz

    client = Boltz(base_url=os.environ.get("BOLTZ_BASE_URL", "https://api.boltz.bio"), api_key=_api_key())

    if args.dry_run:
        inp = _prepare_input(jobs[0]["request"])
        est = client.predictions.structure_and_binding.estimate_cost(model="boltz-2.1", input=inp)
        print(json.dumps(est.model_dump() if hasattr(est, "model_dump") else est, indent=2, sort_keys=True))
        return 0

    submitted: list[dict] = []
    for j in jobs:
        inp = _prepare_input(j["request"])
        name = f"{j['design_id']}_{j['peptide_id']}"[:120]
        pred = client.predictions.structure_and_binding.start(
            model="boltz-2.1",
            input=inp,
            name=name,
        )
        row = {
            "design_id": j["design_id"],
            "peptide_id": j["peptide_id"],
            "prediction_id": pred.id,
            "status": pred.status,
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        submitted.append(row)
        print(f"START {row['prediction_id']} {j['design_id']} {j['peptide_id']} -> {pred.status}")
        if args.sleep:
            time.sleep(args.sleep)

    out = {
        "campaign_id": "NYESO1-A0201-specificity",
        "node": "L1B",
        "n_submitted": len(submitted),
        "jobs": submitted,
    }
    jobs_path = Path(args.jobs_out)
    jobs_path.write_text(json.dumps(out, indent=1, sort_keys=True))
    print(f"WROTE {jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

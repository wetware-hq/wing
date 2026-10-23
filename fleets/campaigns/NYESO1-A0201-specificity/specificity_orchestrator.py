"""Specificity campaign orchestrator: survivors × decoy panel → L2 scores → specificity margin."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import specificity_margin as sm

CAMPAIGN_DIR = Path(__file__).resolve().parent
PARENT = CAMPAIGN_DIR.parent / "NYESO1-A0201"
RUN_ONE = PARENT / "run-one"
DEFAULT_RUN_ONE_ARTIFACTS = RUN_ONE / "artifacts"


def _load_run_one_module(name: str):
    path = RUN_ONE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"PyYAML required to read {path}") from e
    return yaml.safe_load(path.read_text())


def _manifest_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def decoy_peptide_entries(decoy_doc: dict) -> list[dict]:
    """Normalize decoy_panel.yaml (mutants[]) or legacy decoys.entries."""
    entries = (decoy_doc.get("decoys") or {}).get("entries")
    if entries:
        return entries
    return [
        {
            "peptide_id": m["id"],
            "sequence": m.get("sequence"),
            **m,
        }
        for m in decoy_doc.get("mutants", [])
    ]


def collect_peptide_artifact_dirs(survivor_id: str, artifacts_root: Path) -> dict[str, Path]:
    """Map peptide_id -> directory with _predicted.cif / metrics / pae.

    Layout A (run-one cognate only): ``artifacts/<pres_id>/``
    Layout B (post-L1B): ``artifacts/<pres_id>/<peptide_id>/``
    """
    base = artifacts_root / survivor_id
    if not base.is_dir():
        return {}
    out: dict[str, Path] = {}
    if (base / f"{survivor_id}_predicted.cif").is_file() or list(base.glob("*_predicted.cif")):
        out["cognate_SLLMWITQC"] = base
        return out
    for sub in sorted(p for p in base.iterdir() if p.is_dir()):
        if list(sub.glob("*_predicted.cif")):
            out[sub.name] = sub
    return out


def score_survivor_peptides(
    survivor_id: str,
    peptide_dirs: dict[str, Path],
    artifacts_root: Path,
    flags_path: Path,
) -> dict[str, dict]:
    orch = _load_run_one_module("layer2_orchestrator")
    _load_run_one_module("layer2_core")
    _load_run_one_module("contact_analysis")
    tier0 = _load_run_one_module("tier0_targeting")
    flags = tier0.load_flags(flags_path)
    rows: dict[str, dict] = {}
    for peptide_id, pdir in peptide_dirs.items():
        design_id = pdir.name if pdir.name.startswith("pres_") else survivor_id
        rec = orch.score_design(
            design_id,
            pdir,
            artifacts_root,
            flags,
            with_sasa=False,
            with_docking=True,
            with_contact_site=True,
        )
        sm.attach_metrics_inline(rec, pdir / "metrics.json")
        row = sm.row_from_layer2_design(rec)
        row["peptide_id"] = peptide_id
        rows[peptide_id] = row
    return rows


def build_ranked_panel(
    survivors: list[dict],
    decoy_doc: dict,
    artifacts_root: Path,
    flags_path: Path,
    *,
    score: bool,
    stack: tuple[str, ...],
) -> dict:
    cognate_id = decoy_doc["cognate"]["peptide_id"]
    decoy_entries = decoy_peptide_entries(decoy_doc)
    decoy_ids = [e["peptide_id"] for e in decoy_entries]
    panel_ready = decoy_doc.get("panel_ready_for_l1b", False)

    designs_out: list[dict] = []
    for s in survivors:
        sid = s["design_id"]
        entry: dict = {
            "design_id": sid,
            "binder_sequence": s["binder_sequence"],
            "source_job_id": decoy_doc.get("source_job_id", "prot_des_TY6KzyxULq8mACflXbhn"),
        }
        peptide_dirs = collect_peptide_artifact_dirs(sid, artifacts_root)
        if not peptide_dirs:
            entry["margin"] = {"status": "no_artifacts", "reason": "no L1B/L2 artifact dirs found"}
            designs_out.append(entry)
            continue

        if score:
            peptide_rows = list(
                score_survivor_peptides(sid, peptide_dirs, artifacts_root, flags_path).values()
            )
        else:
            bundle_path = artifacts_root / "layer2_bundle.json"
            if sid in _run_one_design_ids(bundle_path) and len(peptide_dirs) == 1:
                peptide_rows = [_run_one_cognate_row(bundle_path, sid, cognate_id)]
            else:
                entry["margin"] = {
                    "status": "incomplete",
                    "reason": "use --score or provide per-peptide artifact tree",
                }
                designs_out.append(entry)
                continue

        margin = sm.compute_specificity_margin(
            peptide_rows,
            cognate_peptide_id=cognate_id,
            decoy_peptide_ids=decoy_ids,
            stack=stack,
        )
        if margin.get("status") == "incomplete":
            margin["panel_ready"] = panel_ready
            if panel_ready:
                margin["note"] = (
                    "Decoy panel signed; margin undefined until L1B decoy refolds complete"
                )
            else:
                margin["note"] = (
                    "OD-3 decoy sequences unsigned; margin undefined until L1B completes"
                )
        entry["margin"] = margin
        designs_out.append(entry)

    designs_out.sort(
        key=lambda d: (
            d.get("margin", {}).get("specificity_margin") is None,
            d.get("margin", {}).get("specificity_margin", 9999),
            d["design_id"],
        ),
    )
    return {
        "schema_version": "1.0.0",
        "campaign_id": "NYESO1-A0201-specificity",
        "primary_endpoint": "specificity_margin",
        "manifest_hash": _manifest_hash(
            CAMPAIGN_DIR / "survivor_panel.yaml",
            CAMPAIGN_DIR / "decoy_panel.yaml",
        ),
        "designs": designs_out,
    }


def _run_one_design_ids(bundle_path: Path) -> set[str]:
    if not bundle_path.is_file():
        return set()
    data = json.loads(bundle_path.read_text())
    return set((data.get("designs") or {}).keys())


def _run_one_cognate_row(bundle_path: Path, design_id: str, cognate_id: str) -> dict:
    data = json.loads(bundle_path.read_text())
    block = data["designs"][design_id]
    metrics = RUN_ONE / "artifacts" / design_id / "metrics.json"
    sm.attach_metrics_inline(block, metrics)
    row = sm.row_from_layer2_design(block)
    row["peptide_id"] = cognate_id
    return row


def transport_payload(ranked: dict, *, top_n: int = 3) -> dict:
    eligible = [
        d
        for d in ranked["designs"]
        if d.get("margin", {}).get("status") == "computed"
    ]
    top = eligible[:top_n]
    return {
        "transport": "T1",
        "direction": "fleet_to_case",
        "campaign_id": ranked["campaign_id"],
        "manifest_hash": ranked["manifest_hash"],
        "top_designs_by_specificity_margin": [
            {
                "design_id": d["design_id"],
                "binder_sequence": d["binder_sequence"],
                "specificity_margin": d["margin"]["specificity_margin"],
                "on_target_rank": d["margin"]["on_target_rank"],
                "best_decoy_rank": d["margin"]["best_decoy_rank"],
                "contact_site": (d["margin"]["peptide_rows"][0].get("contact_site") if d["margin"].get("peptide_rows") else None),
                "provenance": (d["margin"]["peptide_rows"][0] if d["margin"].get("peptide_rows") else {}),
            }
            for d in top
        ],
        "open_decisions": ["OD-1", "OD-4"],
        "resolved_decisions": ["OD-2", "OD-3"],
        "note": "In-vitro work is out of scope; BIO Physician owns the reproduction bar.",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NYESO1-A0201 specificity margin orchestrator")
    ap.add_argument("--survivors", default=str(CAMPAIGN_DIR / "survivor_panel.yaml"))
    ap.add_argument("--decoys", default=str(CAMPAIGN_DIR / "decoy_panel.yaml"))
    ap.add_argument("--artifacts", default=str(DEFAULT_RUN_ONE_ARTIFACTS))
    ap.add_argument("--flags", default=str(PARENT / "targeting_flags.json"))
    ap.add_argument("--ranked-out", default=str(CAMPAIGN_DIR / "artifacts" / "ranked_panel.json"))
    ap.add_argument("--transport-out", default=str(CAMPAIGN_DIR / "artifacts" / "transport_t1.json"))
    ap.add_argument("--score", action="store_true", help="Run layer-2 scoring per peptide dir")
    ap.add_argument(
        "--write-l1b-manifest",
        default=None,
        help="Write L1B predict requests to path (requires filled decoy sequences)",
    )
    args = ap.parse_args(argv)

    survivors_doc = _load_yaml(Path(args.survivors))
    decoy_doc = _load_yaml(Path(args.decoys))
    decoy_doc.setdefault("source_job_id", survivors_doc.get("source_job_id"))

    if args.write_l1b_manifest:
        from l1b_request_builder import write_l1b_manifest

        peptides = [decoy_doc["cognate"]] + [
            e for e in decoy_peptide_entries(decoy_doc) if e.get("sequence")
        ]
        write_l1b_manifest(
            survivors_doc["survivors"],
            peptides,
            Path(args.write_l1b_manifest),
        )
        print(f"WROTE {args.write_l1b_manifest} ({len(peptides)} peptide slots)")
        return 0

    ranked = build_ranked_panel(
        survivors_doc["survivors"],
        decoy_doc,
        Path(args.artifacts),
        Path(args.flags),
        score=args.score,
        stack=sm.DEFAULT_DESCRIPTOR_STACK,
    )
    ranked_path = Path(args.ranked_out)
    ranked_path.parent.mkdir(parents=True, exist_ok=True)
    ranked_path.write_text(sm.canonical_json(ranked))
    transport = transport_payload(ranked)
    Path(args.transport_out).write_text(sm.canonical_json(transport))
    print(f"WROTE {ranked_path}")
    print(f"WROTE {args.transport_out}")
    computed = sum(1 for d in ranked["designs"] if d.get("margin", {}).get("status") == "computed")
    print(f"designs={len(ranked['designs'])} margins_computed={computed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Unified layer-2 orchestrator for NYESO1-A0201 run-one (WP-A–F).

One entrypoint merges ipSAE, Tier 0 G7 metrics, dual item-1 shell reporting (5.0 + 10.0 Å),
item 10 docking, and per-design provenance into ``layer2_bundle.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import item10_docking
import l2_policy
import layer2_core
import tier0_targeting

BUNDLE_VERSION = "1.0.0"
REPORTING_SHELLS = (10.0, 5.0)


def _flags_hash(flags_path: Path) -> str:
    return hashlib.sha256(flags_path.read_bytes()).hexdigest()


def score_design(
    design_id: str,
    design_dir: Path,
    artifacts_root: Path,
    flags: dict,
    flags_path: Path,
    with_sasa: bool,
    with_docking: bool,
) -> dict:
    paths = layer2_core.design_paths(design_dir)
    block: dict = {
        "provenance": layer2_core.provenance_block(design_id, design_dir, artifacts_root),
    }
    if paths["cif"] and paths["pae"]:
        block["ipsae"] = layer2_core.score_ipsae_record(
            design_id,
            paths["cif"],
            paths["pae"],
            paths["metrics"],
        )
    else:
        block["ipsae"] = {"score_error": "missing cif or pae"}

    if paths["cif"]:
        block["tier0"] = tier0_targeting.analyse_design(
            design_id, paths["cif"], flags, with_sasa=with_sasa
        )
        block["item1_shell_reporting"] = {
            str(shell): tier0_targeting.item1_reporting_at_shell(paths["cif"], flags, shell)
            for shell in REPORTING_SHELLS
        }
        if with_docking:
            block["item10_docking"] = item10_docking.measure_design(paths["cif"])
    return block


def run_bundle(
    artifacts_root: Path,
    flags_path: Path,
    *,
    with_sasa: bool = True,
    with_docking: bool = True,
    policies: tuple[str, ...] = (),
) -> dict:
    flags = tier0_targeting.load_flags(flags_path)
    designs: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for d in sorted(p for p in artifacts_root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        try:
            rec = score_design(
                d.name, d, artifacts_root, flags, flags_path, with_sasa, with_docking
            )
            rec["policy"] = l2_policy.evaluate_recorded(rec.get("tier0", {}), policies)
            designs[d.name] = rec
        except Exception as e:  # noqa: BLE001
            errors[d.name] = f"{type(e).__name__}: {e}"

    item10_summary = (
        item10_docking.measure_all(artifacts_root) if with_docking else {"designs": {}, "errors": {}}
    )

    return {
        "schema_version": BUNDLE_VERSION,
        "campaign": "NYESO1-A0201",
        "status": "RECORDED-NON-GATING",
        "gating_warning": (
            "FLEET.toml gating remains iptm and plddt only. All Tier 0, item 10, and "
            "policy results here are recorded or optional CLI policy — not fleet gates."
        ),
        "parameters": {
            "epitope_shell_cutoff_angstrom": flags["epitope_shell_cutoff_angstrom"],
            "contact_cutoff_angstrom": flags["contact_cutoff_angstrom"],
            "item1_reporting_shells_angstrom": list(REPORTING_SHELLS),
            "flags_file": flags_path.name,
            "flags_sha256": _flags_hash(flags_path),
        },
        "pins": layer2_core.LAYER2_PINS,
        "job_id": layer2_core.RUN_ONE_JOB_ID,
        "designs": designs,
        "errors": errors,
        "item10_docking_artifact": item10_summary,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NYESO1-A0201 unified layer-2 orchestrator")
    run_dir = Path(__file__).parent
    ap.add_argument("--artifacts", default=str(run_dir / "artifacts"))
    ap.add_argument("--flags", default=str(run_dir.parent / "targeting_flags.json"))
    ap.add_argument("--bundle-out", default=None, help="default: <artifacts>/layer2_bundle.json")
    ap.add_argument("--legacy-out", default=None, help="optional layer2_results.json path")
    ap.add_argument("--no-sasa", action="store_true")
    ap.add_argument("--no-docking", action="store_true")
    ap.add_argument(
        "--policy",
        action="append",
        default=[],
        help="Optional policies, e.g. buried-anchors-zero (UPGRADES P2; not FLEET.toml)",
    )
    args = ap.parse_args(argv)

    artifacts = Path(args.artifacts)
    flags_path = Path(args.flags)
    bundle_path = Path(args.bundle_out or artifacts / "layer2_bundle.json")

    payload = run_bundle(
        artifacts,
        flags_path,
        with_sasa=not args.no_sasa,
        with_docking=not args.no_docking,
        policies=tuple(args.policy),
    )
    bundle_path.write_text(json.dumps(payload, indent=1, sort_keys=True))

    if args.legacy_out:
        legacy = layer2_core.legacy_ipsae_map(payload["designs"])
        Path(args.legacy_out).write_text(json.dumps(legacy, indent=1, sort_keys=True))

    item10_path = artifacts / "item10_docking_results.json"
    item10_path.write_text(json.dumps(payload["item10_docking_artifact"], indent=1, sort_keys=True))

    violations: list[str] = []
    for did, rec in payload["designs"].items():
        for crit in l2_policy.policy_violations(rec.get("policy", {})):
            violations.append(f"{did}:{crit}")
        t0 = rec.get("tier0") or {}
        if "buried-anchors-zero" in args.policy and t0.get("item_3_buried_anchor_contact_count", 0) != 0:
            print(
                f"POLICY buried-anchors-zero FAILED: {did} "
                f"item_3_buried_anchor_contact_count={t0.get('item_3_buried_anchor_contact_count')} "
                "(UPGRADES.md item 3 / P2 — not FLEET.toml until signed)",
                file=sys.stderr,
            )
            violations.append(f"{did}:item_3_buried_anchor_contact_count")

    print(f"WROTE {bundle_path} ({len(payload['designs'])} designs)")
    if violations:
        return 2
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())

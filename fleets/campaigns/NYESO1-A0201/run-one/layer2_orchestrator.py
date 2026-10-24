"""Unified layer-2 orchestrator for NYESO1-A0201 run-one (WP-A–F).

Canonical artifact: ``artifacts/layer2_bundle.json`` (ipSAE, Tier 0, item 10, contact site,
provenance). Legacy ipSAE-only: ``--ipsae-only`` (container path; replaces ``layer2_eval.py``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import contact_analysis
import layer2_core
import specificity_scoring
import tier0_targeting

BUNDLE_VERSION = "1.2.0"
SPECIFICITY_CAMPAIGN_ID = "NYESO1-A0201-specificity"
REPORTING_SHELLS = (10.0, 5.0)


def _flags_hash(flags_path: Path) -> str:
    return hashlib.sha256(flags_path.read_bytes()).hexdigest()


def score_design(
    design_id: str,
    design_dir: Path,
    artifacts_root: Path,
    flags: dict,
    with_sasa: bool,
    with_docking: bool,
    with_contact_site: bool,
    *,
    decoy_panel: dict | None = None,
    with_specificity: bool = False,
    peptide_sequence: str | None = None,
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
            design_id, paths["cif"], flags, with_sasa=with_sasa,
            peptide_sequence=peptide_sequence,
        )
        block["item1_shell_reporting"] = {
            str(shell): tier0_targeting.item1_reporting_at_shell(
                paths["cif"], flags, shell, peptide_sequence
            )
            for shell in REPORTING_SHELLS
        }
        if with_docking:
            block["item10_docking"] = layer2_core.measure_item10_docking(
                paths["cif"], peptide_sequence
            )
        if with_contact_site:
            block["contact_site"] = contact_analysis.analyse_design(
                design_id, paths["cif"], peptide_sequence=peptide_sequence
            )
        if with_specificity and paths["cif"]:
            seq = specificity_scoring.binder_sequence_from_cif(paths["cif"])
            block["binder_sequence"] = seq
            block["liability_filters"] = specificity_scoring.liability_filters(seq)
            on_target = specificity_scoring.peptide_binder_ipsae(block.get("ipsae") or {})
            decoy_scores: dict[str, float | None] = {}
            if decoy_panel:
                for mut in decoy_panel.get("mutants", []):
                    did = mut["id"]
                    scored = specificity_scoring.score_decoy_complex(
                        design_id,
                        did,
                        artifacts_root,
                        layer2_core.score_ipsae_record,
                    )
                    decoy_scores[did] = scored.get("ipsae_cd")
            block["specificity"] = specificity_scoring.compute_margin(on_target, decoy_scores)
            block["gates"] = specificity_scoring.evaluate_gates(
                block["specificity"],
                block["liability_filters"],
                block.get("tier0") or {},
                block.get("ipsae") or {},
            )
    return block


def run_bundle(
    artifacts_root: Path,
    flags_path: Path,
    *,
    with_sasa: bool = True,
    with_docking: bool = True,
    with_contact_site: bool = True,
    policies: tuple[str, ...] = (),
    decoy_panel_path: Path | None = None,
    with_specificity: bool = False,
    campaign_id: str = "NYESO1-A0201",
) -> dict:
    flags = tier0_targeting.load_flags(flags_path)
    decoy_panel = (
        specificity_scoring.load_decoy_panel(decoy_panel_path) if decoy_panel_path else None
    )
    designs: dict[str, dict] = {}
    errors: dict[str, str] = {}
    tier0_rows: dict[str, dict] = {}
    contact_rows: dict[str, dict] = {}

    design_dirs = sorted(
        p for p in artifacts_root.iterdir() if p.is_dir() and p.name.startswith("pres_")
    )
    # "0 of 0 scored" and "0 of 10 scored" are different facts. Without this, an
    # artifacts root with no design dirs produced a zero-design panel reading
    # "No design cleared the hard gates" and exited 0: a pipeline misconfiguration
    # presented as a scientific result.
    if not design_dirs:
        raise FileNotFoundError(
            f"no pres_* design directories under {artifacts_root}; "
            "nothing was scored, which is a pipeline failure, not an empty panel"
        )
    for d in design_dirs:
        try:
            rec = score_design(
                d.name,
                d,
                artifacts_root,
                flags,
                with_sasa,
                with_docking,
                with_contact_site,
                decoy_panel=decoy_panel,
                with_specificity=with_specificity,
            )
            rec["policy"] = layer2_core.evaluate_l2_policies(rec.get("tier0", {}), policies)
            designs[d.name] = rec
            if "tier0" in rec:
                tier0_rows[d.name] = rec["tier0"]
            if "contact_site" in rec:
                contact_rows[d.name] = rec["contact_site"]
        except Exception as e:  # noqa: BLE001
            errors[d.name] = f"{type(e).__name__}: {e}"

    payload = {
        "schema_version": BUNDLE_VERSION,
        "campaign": campaign_id,
        "status": "RECORDED-NON-GATING",
        "gating_warning": (
            "FLEET.toml gating remains iptm and plddt only. Tier 0, item 10, contact site, "
            "and CLI policy results are recorded or optional — not fleet gates."
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
        "tier0": tier0_targeting.manifest_payload(flags, flags_path, tier0_rows, errors),
        "contact_site": {
            "method_note": (
                "Per-design rows under designs[].contact_site; interpretive rule in "
                "run-one/CONTACTS.md"
            ),
            "cutoff_primary_angstrom": contact_analysis.CUTOFF_PRIMARY,
            "cutoff_sensitivity_angstrom": contact_analysis.CUTOFF_SENSITIVITY,
            "designs": contact_rows,
            "errors": errors,
        },
        "designs": designs,
        "errors": errors,
    }
    if with_specificity:
        payload["status"] = "SPECIFICITY-PANEL"
        payload["primary_endpoint"] = "specificity_margin"
        payload["gating_warning"] = (
            "Specificity campaign: hard gates include specificity_margin >= 0.15, "
            "buried_anchor_contacts == 0, liability_filters.pass (see SPECIFICITY.md)."
        )
        # A design that raised was dropped from `designs` and its error kept only
        # in the bundle, so panel.json showed a clean, consecutively ranked panel
        # with no sign that anything had failed. Carry the errors into the panel
        # and refuse the handoff while any remain.
        payload["panel"] = specificity_scoring.build_panel_payload(
            payload, design_errors=payload.get("errors") or {}
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NYESO1-A0201 unified layer-2 orchestrator")
    run_dir = Path(__file__).parent
    ap.add_argument("--artifacts", default=str(run_dir / "artifacts"))
    ap.add_argument("--flags", default=str(run_dir.parent / "targeting_flags.json"))
    ap.add_argument("--bundle-out", default=None, help="default: <artifacts>/layer2_bundle.json")
    ap.add_argument(
        "--legacy-out",
        default=None,
        help="default: <artifacts>/layer2_results.json when running full bundle",
    )
    ap.add_argument("--ipsae-only", action="store_true", help="ipSAE JSON only (container entry)")
    ap.add_argument("--no-sasa", action="store_true")
    ap.add_argument("--no-docking", action="store_true")
    ap.add_argument("--no-contact-site", action="store_true")
    ap.add_argument(
        "--policy",
        action="append",
        default=[],
        help="Optional policies, e.g. buried-anchors-zero (UPGRADES P2; not FLEET.toml)",
    )
    ap.add_argument(
        "--specificity-campaign",
        action="store_true",
        help="Enable specificity margin + liability filters + ranked PANEL JSON",
    )
    ap.add_argument(
        "--decoy-panel",
        default=None,
        help="Path to decoy_panel.yaml (default: NYESO1-A0201-specificity/decoy_panel.yaml)",
    )
    ap.add_argument(
        "--panel-out",
        default=None,
        help="Ranked PANEL JSON path (default: <artifacts>/panel.json)",
    )
    ap.add_argument(
        "--rejections-out",
        default=None,
        help="Rejection store JSONL path (default: <artifacts>/rejections.jsonl)",
    )
    args = ap.parse_args(argv)

    artifacts = Path(args.artifacts)
    if args.ipsae_only:
        out = Path(args.legacy_out or artifacts / "layer2_results.json")
        code = layer2_core.write_ipsae_only(artifacts, out)
        print(f"WROTE {out}")
        return code

    flags_path = Path(args.flags)
    bundle_path = Path(args.bundle_out or artifacts / "layer2_bundle.json")
    decoy_path: Path | None = None
    if args.specificity_campaign:
        default_decoy = (
            run_dir.parent.parent
            / "NYESO1-A0201-specificity"
            / "decoy_panel.yaml"
        )
        decoy_path = Path(args.decoy_panel or default_decoy)

    payload = run_bundle(
        artifacts,
        flags_path,
        with_sasa=not args.no_sasa,
        with_docking=not args.no_docking,
        with_contact_site=not args.no_contact_site,
        policies=tuple(args.policy),
        decoy_panel_path=decoy_path,
        with_specificity=args.specificity_campaign,
        campaign_id=SPECIFICITY_CAMPAIGN_ID if args.specificity_campaign else "NYESO1-A0201",
    )
    bundle_path.write_text(json.dumps(payload, indent=1, sort_keys=True))

    if args.specificity_campaign and payload.get("panel"):
        panel_path = Path(args.panel_out or artifacts / "panel.json")
        panel_path.write_text(json.dumps(payload["panel"], indent=1, sort_keys=True))
        print(f"WROTE {panel_path} (ranked PANEL)")
        # FLEET.toml [rejections] declares this store and nothing wrote it, so an
        # empty file read as "nothing was rejected" rather than "never recorded".
        rejections_path = Path(args.rejections_out or artifacts / "rejections.jsonl")
        n_rejected = specificity_scoring.write_rejections(payload["panel"], rejections_path)
        print(f"WROTE {rejections_path} ({n_rejected} rejection records)")
        pins = (payload["panel"].get("config_pins") or {})
        if not pins.get("all_pinned", False):
            print(
                "HANDOFF BLOCKED (unpinned gates): "
                + ", ".join(pins.get("unpinned_gates") or ["unknown"])
            )
            for f in pins.get("findings") or []:
                print(f"  - [{f.get('gate')}] {f.get('detail')}")

    legacy_path = Path(args.legacy_out or artifacts / "layer2_results.json")
    legacy_path.write_text(
        json.dumps(layer2_core.legacy_ipsae_map(payload["designs"]), indent=1, sort_keys=True)
    )

    violations: list[str] = []
    for did, rec in payload["designs"].items():
        violations.extend(layer2_core.policy_violations(rec.get("policy", {})))
        t0 = rec.get("tier0") or {}
        if "buried-anchors-zero" in args.policy:
            # Zero is the passing value, so an absent count must not default to
            # 0: that silently reports a design nobody measured as compliant.
            n = t0.get("item_3_buried_anchor_contact_count")
            if n is None:
                print(
                    f"POLICY buried-anchors-zero UNMEASURED: {did} "
                    "item_3_buried_anchor_contact_count absent (tier 0 did not "
                    "produce it); not treated as compliant",
                    file=sys.stderr,
                )
                violations.append(f"{did}:item_3_buried_anchor_contact_count:unmeasured")
            elif n != 0:
                print(
                    f"POLICY buried-anchors-zero FAILED: {did} "
                    f"item_3_buried_anchor_contact_count={n} "
                    "(UPGRADES.md item 3 / P2 — not FLEET.toml until signed)",
                    file=sys.stderr,
                )
                violations.append(f"{did}:item_3_buried_anchor_contact_count")

    print(f"WROTE {bundle_path} ({len(payload['designs'])} designs)")
    print(f"WROTE {legacy_path} (legacy ipSAE)")
    if violations:
        return 2
    return 0 if not payload["errors"] else 1


if __name__ == "__main__":
    # Container: LAYER2_ARTIFACTS=/artifacts and argv may be empty.
    if os.environ.get("LAYER2_IPSAE_ONLY") == "1":
        sys.exit(main(["--ipsae-only"]))
    sys.exit(main())

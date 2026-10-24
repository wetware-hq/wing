"""Specificity campaign orchestrator: survivors × decoy panel → L2 scores → specificity margin."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import config_pins
import specificity_margin as sm

CAMPAIGN_DIR = Path(__file__).resolve().parent
PARENT = CAMPAIGN_DIR.parent / "NYESO1-A0201"
RUN_ONE = PARENT / "run-one"
DEFAULT_RUN_ONE_ARTIFACTS = RUN_ONE / "artifacts"


def _load_run_one_module(name: str):
    """Load a run-one module by path, under its bare name.

    The run-one modules import EACH OTHER by bare name at module scope
    (layer2_orchestrator imports contact_analysis, layer2_core, specificity_scoring
    and tier0_targeting). Loading one by path alone therefore raised
    ModuleNotFoundError for its siblings unless the caller happened to have run-one/
    on PYTHONPATH. Putting run-one/ on sys.path once fixes that at the root, and makes
    the load order here irrelevant rather than load-bearing.
    """
    run_one = str(RUN_ONE)
    if run_one not in sys.path:
        sys.path.insert(0, run_one)
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


COGNATE_PEPTIDE_ID = "cognate_SLLMWITQC"


def _peptide_subdirs(base: Path) -> dict[str, Path]:
    """Per-peptide child dirs of ``base`` that hold a prediction, keyed by dir name."""
    if not base.is_dir():
        return {}
    return {
        sub.name: sub
        for sub in sorted(p for p in base.iterdir() if p.is_dir())
        if list(sub.glob("*_predicted.cif"))
    }


def collect_peptide_artifact_dirs(survivor_id: str, artifacts_root: Path) -> dict[str, Path]:
    """Map peptide_id -> directory with _predicted.cif / metrics / pae.

    Three on-disk layouts coexist in this campaign and all are collected, because the
    cognate refold and the decoy refolds live in *separate* trees:

    * **Cognate (run-one):** ``artifacts/<pres_id>/`` with the ``*_predicted.cif`` sitting
      directly in it. Keyed ``cognate_SLLMWITQC``.
    * **Decoys (L1B):** ``artifacts/decoy_refolds/<pres_id>/<peptide_id>/``, the layout
      written by ``l1b_runner.py:mirror_prediction_to_decoy_dir``.
    * **Legacy per-peptide subtree:** ``artifacts/<pres_id>/<peptide_id>/``.

    Finding the shallow cognate ``.cif`` must not short-circuit the walk: doing so was
    the Path B reader bug that hid all 100 L1B decoy dirs from ``ranked_panel.json``.
    """
    out: dict[str, Path] = {}
    base = artifacts_root / survivor_id
    if base.is_dir():
        if (base / f"{survivor_id}_predicted.cif").is_file() or list(base.glob("*_predicted.cif")):
            out[COGNATE_PEPTIDE_ID] = base
        out.update(_peptide_subdirs(base))
    out.update(_peptide_subdirs(artifacts_root / "decoy_refolds" / survivor_id))
    return out


def score_survivor_peptides(
    survivor_id: str,
    peptide_dirs: dict[str, Path],
    artifacts_root: Path,
    flags_path: Path,
    peptide_sequences: dict[str, str] | None = None,
) -> dict[str, dict]:
    # Dependencies first, dependent last. Not strictly required now that
    # _load_run_one_module puts run-one/ on sys.path, but it keeps the dependency
    # direction visible at the call site.
    _load_run_one_module("contact_analysis")
    _load_run_one_module("layer2_core")
    tier0 = _load_run_one_module("tier0_targeting")
    orch = _load_run_one_module("layer2_orchestrator")
    flags = tier0.load_flags(flags_path)
    peptide_sequences = peptide_sequences or {}
    rows: dict[str, dict] = {}
    for peptide_id, pdir in peptide_dirs.items():
        design_id = pdir.name if pdir.name.startswith("pres_") else survivor_id
        # Each refold carries ITS OWN chain-C sequence: the cognate for the cognate dir,
        # the mutant for each decoy dir. assert_layout is checked against that expected
        # sequence rather than the cognate's, so the guard still fires on a genuinely
        # mislabelled structure instead of being switched off for decoys.
        rec = orch.score_design(
            design_id,
            pdir,
            artifacts_root,
            flags,
            with_sasa=False,
            with_docking=True,
            with_contact_site=True,
            peptide_sequence=peptide_sequences.get(peptide_id),
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
    # An empty decoy panel is not a panel. Without this the run got as far as
    # ranking and died on min() of an empty sequence, naming neither the
    # campaign nor the real cause.
    if not decoy_ids:
        raise SystemExit(
            "decoy panel is empty: no 'decoys.entries' and no 'mutants' in the decoy "
            "document; a specificity margin against zero decoys is not a margin"
        )
    duplicate_ids = sorted({i for i in decoy_ids if decoy_ids.count(i) > 1})
    if duplicate_ids:
        raise SystemExit(f"decoy panel has duplicate peptide_ids: {duplicate_ids}")
    if cognate_id in decoy_ids:
        raise SystemExit(
            f"cognate peptide_id {cognate_id!r} also appears in the decoy panel; "
            "the on-target peptide cannot be its own decoy"
        )
    panel_ready = decoy_doc.get("panel_ready_for_l1b", False)

    # peptide_id -> the chain-C sequence that peptide's refold must carry.
    peptide_sequences: dict[str, str] = {cognate_id: decoy_doc["cognate"]["sequence"]}
    for e in decoy_entries:
        if e.get("sequence"):
            peptide_sequences[e["peptide_id"]] = e["sequence"]

    designs_out: list[dict] = []
    for s in survivors:
        sid = s["design_id"]
        entry: dict = {
            "design_id": sid,
            "binder_sequence": s["binder_sequence"],
            # No hardcoded fallback: a guessed job id stamped run-one's
            # provenance onto every design regardless of which job actually
            # produced the artifacts. Absent provenance reports as null.
            "source_job_id": decoy_doc.get("source_job_id"),
        }
        peptide_dirs = collect_peptide_artifact_dirs(sid, artifacts_root)
        if not peptide_dirs:
            entry["margin"] = {"status": "no_artifacts", "reason": "no L1B/L2 artifact dirs found"}
            designs_out.append(entry)
            continue

        if score:
            peptide_rows = list(
                score_survivor_peptides(
                    sid, peptide_dirs, artifacts_root, flags_path, peptide_sequences
                ).values()
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
            d.get("margin", {}).get("rank_margin") is None,
            d.get("margin", {}).get("rank_margin", 9999),
            d["design_id"],
        ),
    )
    return {
        "schema_version": "1.0.0",
        "campaign_id": "NYESO1-A0201-specificity",
        "primary_endpoint": "rank_margin (ordinal; audit-only, NOT the Path A specificity_margin gated at >= 0.15)",
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


def _cognate_row(design: dict) -> dict | None:
    """The on-target peptide's row for a design, selected by id rather than position."""
    margin = design.get("margin") or {}
    cognate_id = margin.get("on_target_peptide_id") or COGNATE_PEPTIDE_ID
    for row in margin.get("peptide_rows") or []:
        if row.get("peptide_id") == cognate_id:
            return row
    return None


def transport_payload(
    ranked: dict, *, top_n: int = 3, config_pins_report: dict | None = None
) -> dict:
    # status == "computed" only means the margin is defined, not that the design
    # passed. The T1 handoff must gate on the verdict: pass_in_silico_draft is
    # true only when the cognate outranks every decoy in the panel.
    # Only the full declared descriptor stack counts. "computed_reduced_stack"
    # is an honest number from fewer descriptors, which is fine for audit and
    # not fine for a handoff.
    computed = [
        d
        for d in ranked["designs"]
        if d.get("margin", {}).get("status") == "computed"
    ]
    eligible = [
        d for d in computed if d["margin"].get("pass_in_silico_draft") is True
    ]
    # A gate declared active in FLEET.toml whose inputs are unpinned has not been
    # evaluated, so nothing may be handed off on the strength of it passing.
    # `or {...all_pinned: True}` turned an absent report into "everything is
    # pinned", so any caller but main() got a populated handoff with no gate
    # evaluation behind it. Absent is now an error, not a pass.
    if config_pins_report is None:
        raise ValueError(
            "config_pins_report is required: a handoff cannot be built without "
            "evaluating whether the declared gates have pinned inputs"
        )
    pins = config_pins_report
    blocked_by_unpinned = not pins.get("all_pinned", True)
    top = [] if blocked_by_unpinned else eligible[:top_n]
    excluded = [
        {
            "design_id": d["design_id"],
            "status": d.get("margin", {}).get("status"),
            "rank_margin": d.get("margin", {}).get("rank_margin"),
            "reason": (
                "cognate does not outrank every decoy"
                if d in computed
                else d.get("margin", {}).get("reason")
                or (
                    "margin from a reduced descriptor stack: "
                    + ", ".join(
                        sorted((d.get("margin", {}).get("excluded_descriptors") or {}))
                    )
                    + " incomplete across the panel"
                    if d.get("margin", {}).get("status") == "computed_reduced_stack"
                    else "margin undefined"
                )
            ),
        }
        for d in ranked["designs"]
        if d not in eligible
    ]
    return {
        "transport": "T1",
        "direction": "fleet_to_case",
        "campaign_id": ranked["campaign_id"],
        "manifest_hash": ranked["manifest_hash"],
        "top_designs_by_rank_margin": [
            {
                "design_id": d["design_id"],
                "binder_sequence": d["binder_sequence"],
                "rank_margin": d["margin"]["rank_margin"],
                "on_target_rank": d["margin"]["on_target_rank"],
                "best_decoy_rank": d["margin"]["best_decoy_rank"],
                # Select the cognate row by peptide_id. Taking [0] was correct
                # only by insertion-order accident: any reordering would have
                # put a DECOY's contact site and provenance in the handoff.
                "contact_site": (_cognate_row(d) or {}).get("contact_site"),
                "provenance": _cognate_row(d) or {},
            }
            for d in top
        ],
        "gate": "margin.pass_in_silico_draft",
        "eligible_count": len(eligible),
        "config_pins": pins,
        "handoff_blocked_by_unpinned_gates": blocked_by_unpinned,
        "handoff_block_reason": (
            "declared gates "
            + ", ".join(pins.get("unpinned_gates") or [])
            + " have unpinned inputs and were never evaluated"
            if blocked_by_unpinned
            else None
        ),
        "excluded_designs": excluded,
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
        "--require-pinned",
        action="store_true",
        help="Fail the run if a gate declared active in FLEET.toml has unpinned inputs",
    )
    ap.add_argument(
        "--write-l1b-manifest",
        default=None,
        help="Write L1B predict requests to path (requires filled decoy sequences)",
    )
    args = ap.parse_args(argv)

    survivors_doc = _load_yaml(Path(args.survivors))
    decoy_doc = _load_yaml(Path(args.decoys))
    # survivors_doc can be None when the YAML is empty; .get would raise.
    decoy_doc.setdefault("source_job_id", (survivors_doc or {}).get("source_job_id"))

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
    pins_report = config_pins.collect_unpinned(CAMPAIGN_DIR / "FLEET.toml", CAMPAIGN_DIR)
    if args.require_pinned and not pins_report["all_pinned"]:
        config_pins.require_pinned(CAMPAIGN_DIR / "FLEET.toml", CAMPAIGN_DIR)
    transport = transport_payload(ranked, config_pins_report=pins_report)
    Path(args.transport_out).write_text(sm.canonical_json(transport))
    print(f"WROTE {ranked_path}")
    print(f"WROTE {args.transport_out}")
    designs = ranked["designs"]
    statuses = [(d.get("margin") or {}).get("status") for d in designs]
    computed = sum(1 for st in statuses if st == "computed")
    reduced = sum(1 for st in statuses if st == "computed_reduced_stack")
    print(
        f"designs={len(designs)} margins_computed={computed} "
        f"margins_reduced_stack={reduced}"
    )
    if not pins_report["all_pinned"]:
        print(
            "UNPINNED GATES (handoff blocked): "
            + ", ".join(pins_report["unpinned_gates"])
        )
        for f in pins_report["findings"]:
            print(f"  - [{f['gate']}] {f['detail']}")
    # Both artifacts were written unconditionally and main returned 0 on every
    # path, so a run in which NO design scored still produced a well-formed
    # ranked panel and a success exit code; only a stdout line dissented, and
    # nothing read it. A run that scored nothing is a failed run.
    scored = computed + reduced
    if not designs:
        print("FAILED: no designs in the ranked panel")
        return 2
    if scored == 0:
        print(f"FAILED: no margin was computed for any of {len(designs)} designs")
        return 2
    if scored < len(designs):
        unscored = [
            d["design_id"] for d, st in zip(designs, statuses)
            if st not in ("computed", "computed_reduced_stack")
        ]
        print(f"FAILED: {len(unscored)} of {len(designs)} designs have no margin: {unscored}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

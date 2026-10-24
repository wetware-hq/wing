"""Specificity margin + developability liability filters (pure CPU, Layer 2)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from contact_analysis import BINDER_CHAIN, assert_layout, load_chains

DEFAULT_MOTIFS = ["NG", "NS", "NT", "NH", "DG", "DS", "DT", r"N[^P][ST]"]
# FLEET.toml [liability_filters] declares these two as hard_fail. They were
# declared and never implemented, so a binder carrying either was emitted with
# liability_filters.pass = true, and that value is one of the three hard gates.
DEFAULT_POLY_Q_MAX_RUN = 2
SPECIFICITY_MARGIN_GATE = 0.15
SOFT_IPTM = 0.60
SOFT_PLDDT_D = 80.0


def load_decoy_panel(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def binder_sequence_from_cif(cif_path: Path) -> str:
    import gemmi

    chains = load_chains(cif_path)
    assert_layout(chains, cif_path)
    ch = chains[BINDER_CHAIN]
    return gemmi.one_letter_code(
        [ch.residue_names[i] for i in sorted(ch.residue_names)]
    ).upper()


def peptide_binder_ipsae(ipsae_block: dict[str, Any]) -> float | None:
    """Peptide–binder ipSAE (chain C|D min ipSAE, same as run-one ``ipsae_CD_min``)."""
    if ipsae_block.get("score_error"):
        return None
    dpairs = ipsae_block.get("min_ipsae_D_pairs") or {}
    for key in ("C|D", "D|C"):
        if key in dpairs and dpairs[key] is not None:
            return float(dpairs[key])
    pairs = ipsae_block.get("pairs") or {}
    for key in ("C|D", "D|C"):
        if key in pairs and pairs[key].get("min_ipsae") is not None:
            return float(pairs[key]["min_ipsae"])
    return None


def scan_motifs(sequence: str, patterns: list[str] | None = None) -> list[dict[str, str]]:
    patterns = patterns or DEFAULT_MOTIFS
    hits: list[dict[str, str]] = []
    for pat in patterns:
        for m in re.finditer(pat, sequence):
            hits.append({"motif": pat, "match": m.group(0), "start": str(m.start())})
    return hits


def liability_filters(
    sequence: str,
    *,
    motif_patterns: list[str] | None = None,
    oxidation_residues: tuple[str, ...] = ("M", "W"),
    oxidation_threshold: int = 1,
    sap_mode: str = "soft",
    poly_q_max_run: int = DEFAULT_POLY_Q_MAX_RUN,
) -> dict[str, Any]:
    motifs = scan_motifs(sequence, motif_patterns)
    cys_count = sequence.count("C")
    unpaired_cys_fail = cys_count > 0
    ox_count = sum(sequence.count(r) for r in oxidation_residues)
    oxidation_fail = ox_count >= oxidation_threshold
    # N-terminal Gln cyclises to pyroglutamate, so it is a hard fail on its own.
    n_term_gln_fail = sequence[:1].upper() == "Q"
    longest_q_run = max((len(m.group(0)) for m in re.finditer(r"Q+", sequence)), default=0)
    poly_q_fail = longest_q_run > poly_q_max_run
    sap_note = "skipped_no_sap"
    sap_soft_fail = False

    hard_fail = (
        bool(motifs)
        or unpaired_cys_fail
        or oxidation_fail
        or n_term_gln_fail
        or poly_q_fail
    )
    score = 1.0 - 0.15 * len(motifs)
    if sap_soft_fail:
        score -= 0.1
    score = max(0.0, round(score, 4))

    return {
        "pass": not hard_fail,
        "developability_score": score,
        "motif_hits": motifs,
        "unpaired_cys": {"count": cys_count, "hard_fail": unpaired_cys_fail},
        "exposed_oxidation": {
            "residue_counts": {r: sequence.count(r) for r in oxidation_residues},
            "threshold": oxidation_threshold,
            "sequence_proxy": True,
            "hard_fail": oxidation_fail,
        },
        "n_terminal_glutamine": {
            "residue": sequence[:1].upper() or None,
            "hard_fail": n_term_gln_fail,
        },
        "poly_q": {
            "longest_run": longest_q_run,
            "max_run": poly_q_max_run,
            "hard_fail": poly_q_fail,
        },
        "sap_patch": {"mode": sap_mode, "status": sap_note, "soft_fail": sap_soft_fail},
        "allow": "none",
    }


def decoy_refold_dir(artifacts_root: Path, design_id: str, decoy_id: str) -> Path:
    return artifacts_root / "decoy_refolds" / design_id / decoy_id


def score_decoy_complex(
    design_id: str,
    decoy_id: str,
    artifacts_root: Path,
    score_ipsae_fn,
) -> dict[str, Any]:
    """Score one decoy refold if mirrored on disk."""
    import layer2_core

    ddir = decoy_refold_dir(artifacts_root, design_id, decoy_id)
    if not ddir.is_dir():
        return {"decoy_id": decoy_id, "status": "missing", "ipsae_cd": None}
    paths = layer2_core.design_paths(ddir)
    if not paths["cif"] or not paths["pae"]:
        cif_candidates = list(ddir.glob("*_predicted.cif"))
        if cif_candidates:
            paths["cif"] = cif_candidates[0]
        if (ddir / "pae.npz").is_file():
            paths["pae"] = ddir / "pae.npz"
    if not paths["cif"] or not paths["pae"]:
        return {"decoy_id": decoy_id, "status": "incomplete", "ipsae_cd": None}
    block = score_ipsae_fn(design_id, paths["cif"], paths["pae"], paths["metrics"])
    return {
        "decoy_id": decoy_id,
        "status": "scored",
        "ipsae_cd": peptide_binder_ipsae(block),
        "artifact_paths": {
            "predicted_cif": str(paths["cif"].relative_to(artifacts_root)),
            "pae_npz": str(paths["pae"].relative_to(artifacts_root)),
        },
    }


def compute_margin(
    on_target: float | None,
    decoy_scores: dict[str, float | None],
) -> dict[str, Any]:
    if on_target is None:
        return {
            "on_target_ipsae_cd": None,
            "best_decoy_ipsae_cd": None,
            "specificity_margin": None,
            "on_target_rank": None,
            "best_decoy_rank": None,
            "rank_margin": None,
            "margin_status": "missing_on_target_score",
        }
    present = {k: v for k, v in decoy_scores.items() if v is not None}
    missing = sorted(k for k, v in decoy_scores.items() if v is None)
    if not present:
        return {
            "on_target_ipsae_cd": on_target,
            "best_decoy_ipsae_cd": None,
            "specificity_margin": None,
            "on_target_rank": None,
            "best_decoy_rank": None,
            "rank_margin": None,
            "margin_status": "pending_l1b",
            "decoy_scores": decoy_scores,
        }
    best_decoy = max(present.values())
    best_id = max(present, key=present.get)
    margin = round(on_target - best_decoy, 6)
    ranked = sorted(
        [("cognate", on_target)] + list(present.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    ranks = {name: i + 1 for i, (name, _) in enumerate(ranked)}
    on_rank = ranks["cognate"]
    best_decoy_rank = ranks[best_id]
    rank_margin = best_decoy_rank - on_rank
    return {
        "on_target_ipsae_cd": on_target,
        "best_decoy_ipsae_cd": best_decoy,
        "best_decoy_id": best_id,
        "specificity_margin": margin,
        "on_target_rank": on_rank,
        "best_decoy_rank": best_decoy_rank,
        "rank_margin": rank_margin,
        "rank_margin_fleet_text": on_rank - best_decoy_rank,
        # A margin computed against a SUBSET of the panel is not the margin. The
        # best decoy may be one that failed to score, so report coverage and
        # refuse to call a partial panel "computed".
        "margin_status": "computed" if not missing else "partial_decoy_panel",
        "decoy_panel_size": len(decoy_scores),
        "decoys_scored": len(present),
        "decoys_missing": missing,
        "decoy_scores": decoy_scores,
    }


def evaluate_gates(
    specificity: dict[str, Any],
    liability: dict[str, Any],
    tier0: dict[str, Any],
    ipsae_block: dict[str, Any],
) -> dict[str, Any]:
    fails: list[str] = []
    margin = specificity.get("specificity_margin")
    if margin is None:
        fails.append("specificity_margin:pending")
    elif margin < SPECIFICITY_MARGIN_GATE:
        fails.append(f"specificity_margin:{margin}<{SPECIFICITY_MARGIN_GATE}")
    # margin_status was reported but never gated on. A margin from a partial
    # decoy panel is a real number against the wrong denominator, so it has to
    # fail the gate rather than merely be labelled.
    partial_panel = specificity.get("margin_status") == "partial_decoy_panel"
    if partial_panel:
        missing = specificity.get("decoys_missing") or []
        fails.append(f"decoy_panel:incomplete({len(missing)} unscored)")
    # Zero buried anchor contacts is the PASSING value, so an absent count must
    # not default to 0: tier0 analysis can fail and leave the key out entirely,
    # and reading that as a clean pass is how an unmeasured design clears a hard
    # gate. Absent means unmeasured, which fails.
    buried = tier0.get("item_3_buried_anchor_contact_count")
    if buried is None:
        fails.append("buried_anchor_contacts:unmeasured")
    elif buried != 0:
        fails.append("buried_anchor_contacts:nonzero")
    if not liability.get("pass", False):
        fails.append("liability_filters:fail")
    iptm = ipsae_block.get("iptm")
    chain_d = (ipsae_block.get("chain_mean_plddt") or {}).get("D")
    soft_iptm = iptm is not None and iptm >= SOFT_IPTM
    soft_plddt = chain_d is not None and chain_d >= SOFT_PLDDT_D
    hard_pass = (
        margin is not None
        and margin >= SPECIFICITY_MARGIN_GATE
        and buried == 0
        and not partial_panel
        and liability.get("pass", False)
    )
    return {
        "hard_pass": hard_pass,
        "soft_pass": soft_iptm and soft_plddt,
        "fail_reasons": fails,
    }


def rank_panel_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(row: dict[str, Any]) -> tuple:
        spec = row.get("specificity") or {}
        margin = spec.get("specificity_margin")
        margin_key = margin if margin is not None else -1e9
        # The outer default never fired (the key is always present, sometimes
        # None) so this raised AttributeError on a CIF-less design, outside the
        # per-design try. The inner default fabricated a score of 0.0 for an
        # unmeasured design and quietly set the secondary sort key with it.
        dev_raw = (row.get("liability_filters") or {}).get("developability_score")
        dev = dev_raw if dev_raw is not None else -1e9
        # `or -1e9` turned an honest iptm of 0.0 into the sentinel.
        iptm_raw = row.get("iptm")
        iptm = iptm_raw if iptm_raw is not None else -1e9
        return (-margin_key, -dev, -iptm)

    return sorted(rows, key=sort_key)


SPECIFICITY_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[2] / "NYESO1-A0201-specificity"
)


def load_config_pins_report(campaign_dir: Path | None = None) -> dict[str, Any]:
    """Report which declared gates have unpinned inputs, failing CLOSED.

    Path B refused to hand off while a declared gate was unpinned; Path A, which
    is the path whose panel.json actually carries the handoff block, never
    consulted the check at all. If the check itself cannot be run, that is not a
    pass: an unrunnable check reports all_pinned False so the handoff still
    blocks, because the one thing we must never emit is a green we did not earn.
    """
    campaign_dir = campaign_dir or SPECIFICITY_CAMPAIGN_DIR
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_config_pins", campaign_dir / "config_pins.py"
        )
        if spec is None or spec.loader is None:
            raise FileNotFoundError(campaign_dir / "config_pins.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.collect_unpinned(campaign_dir / "FLEET.toml", campaign_dir)
    except Exception as exc:  # noqa: BLE001 - any failure here must block, not pass
        return {
            "checked": [],
            "unpinned_gates": ["config_pins_check_unavailable"],
            "findings": [
                {
                    "gate": "config_pins_check_unavailable",
                    "declared_active_by": "specificity_scoring.load_config_pins_report",
                    "detail": (
                        "the unpinned-gate check could not be run, so no gate can be "
                        f"shown to be pinned: {type(exc).__name__}: {exc}"
                    ),
                }
            ],
            "all_pinned": False,
        }


def build_panel_payload(
    bundle: dict[str, Any],
    *,
    campaign_id: str = "NYESO1-A0201-specificity",
    handoff_top_n: int = 3,
    api_contract_version: str = "v2026-03-01",
    config_pins_report: dict[str, Any] | None = None,
    design_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for design_id, rec in bundle.get("designs", {}).items():
        ipsae = rec.get("ipsae") or {}
        row = {
            "design_id": design_id,
            "binder_sequence": rec.get("binder_sequence"),
            "provenance": rec.get("provenance"),
            "iptm": ipsae.get("iptm"),
            "chain_D_plddt_mean": (ipsae.get("chain_mean_plddt") or {}).get("D"),
            "liability_filters": rec.get("liability_filters"),
            "developability_score": (rec.get("liability_filters") or {}).get("developability_score"),
            "specificity": rec.get("specificity"),
            "tier0": rec.get("tier0"),
            "contact_site": rec.get("contact_site"),
            "gates": rec.get("gates"),
        }
        rows.append(row)
    ranked = rank_panel_rows(rows)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    # A design that fails a hard gate is not a candidate. Filter the handoff on
    # gates.hard_pass rather than on rank, and carry the excluded designs with
    # their reasons so "rejected for developability reasons" is a first-class,
    # readable output instead of a silent omission. An empty handoff is a valid
    # and meaningful result.
    eligible = [r for r in ranked if (r.get("gates") or {}).get("hard_pass") is True]
    pins = config_pins_report if config_pins_report is not None else load_config_pins_report()
    blocked_by_unpinned = not pins.get("all_pinned", False)
    # A design that raised during scoring never reached `designs`, so the panel
    # looked complete and consecutively ranked. An incomplete panel cannot be
    # handed off, and the errors have to travel with it.
    errors = dict(design_errors or {})
    blocked = blocked_by_unpinned or bool(errors)
    handoff = [] if blocked else eligible[:handoff_top_n]
    excluded = [
        {
            "design_id": r["design_id"],
            "rank": r.get("rank"),
            "fail_reasons": (r.get("gates") or {}).get("fail_reasons") or ["gates:absent"],
        }
        for r in ranked
        if r not in eligible
    ]
    return {
        "schema_version": "1.0.0",
        "campaign_id": campaign_id,
        "primary_endpoint": "specificity_margin",
        "ranking": {
            "primary": "specificity_margin",
            "secondary": "developability_score",
            "tertiary": "iptm",
        },
        "pins": {
            **bundle.get("pins", {}),
            "api_contract_version": api_contract_version,
        },
        "designs": ranked,
        "config_pins": pins,
        "design_errors": errors,
        "handoff": {
            "top_n": handoff_top_n,
            "recipient": "Clinical lead",
            "gate": "gates.hard_pass",
            "eligible_count": len(eligible),
            "designs": handoff,
            "excluded": excluded,
            "blocked_by_unpinned_gates": blocked_by_unpinned,
            "blocked_by_design_errors": sorted(errors),
            "note": _handoff_note(blocked_by_unpinned, pins, eligible, errors),
        },
    }


# ---------------------------------------------------------------- rejections
# FLEET.toml [rejections] declares first_class = true, a store at
# artifacts/rejections.jsonl and a closed reason_taxonomy. Nothing wrote that
# file, so the campaign's headline output -- "candidate rejected for
# developability reasons" as a schema-tracked record -- was an empty file that
# read as "nothing was rejected".
REASON_TAXONOMY = (
    "liability",
    "manufacturability",
    "specificity_margin",
    "developability",
    "immunogenicity_safety",
    "adversary_prefilter",
    "format_triad",
)

# Prefix of a gate fail_reason -> reason_code in the declared taxonomy.
_REASON_CODES = (
    ("liability_filters:", "liability"),
    ("specificity_margin:", "specificity_margin"),
    ("decoy_panel:", "specificity_margin"),
    ("manufacturability", "manufacturability"),
)


def classify_fail_reasons(fail_reasons: list[str]) -> dict[str, Any]:
    """Map gate fail reasons onto the declared taxonomy, naming what will not map.

    The taxonomy in FLEET.toml is closed, and not every hard gate has a code in
    it: buried_anchor_contacts is a Tier 0 targeting criterion with no matching
    reason_code. Silently dropping those would make a rejection record look
    complete when it is not, so they are carried verbatim under
    unclassified_fail_reasons instead.
    """
    codes: list[str] = []
    unclassified: list[str] = []
    for reason in fail_reasons:
        for prefix, code in _REASON_CODES:
            if reason.startswith(prefix):
                if code not in codes:
                    codes.append(code)
                break
        else:
            unclassified.append(reason)
    return {"reason_codes": codes, "unclassified_fail_reasons": unclassified}


def rejection_records(
    panel: dict[str, Any], *, stage: str = "layer2_output_schema_pre_judge"
) -> list[dict[str, Any]]:
    """One structured rejection record per design that did not reach the handoff."""
    by_id = {d.get("design_id"): d for d in panel.get("designs") or []}
    handed_off = {d.get("design_id") for d in (panel.get("handoff") or {}).get("designs") or []}
    records: list[dict[str, Any]] = []
    for entry in (panel.get("handoff") or {}).get("excluded") or []:
        did = entry.get("design_id")
        if did in handed_off:
            continue
        row = by_id.get(did) or {}
        fail_reasons = entry.get("fail_reasons") or []
        records.append(
            {
                "schema_version": "1.0.0",
                "campaign_id": panel.get("campaign_id"),
                "design_id": did,
                "stage": stage,
                "rank": entry.get("rank"),
                "fail_reasons": fail_reasons,
                **classify_fail_reasons(fail_reasons),
                "specificity_margin": (row.get("specificity") or {}).get("specificity_margin"),
                "developability_score": row.get("developability_score"),
                "binder_sequence": row.get("binder_sequence"),
            }
        )
    # A design can also be blocked by an unpinned gate rather than by its own
    # merits. That is a reason it did not reach the recipient and belongs here.
    pins = panel.get("config_pins") or {}
    if not pins.get("all_pinned", False):
        for did in by_id:
            if did in handed_off:
                continue
            records.append(
                {
                    "schema_version": "1.0.0",
                    "campaign_id": panel.get("campaign_id"),
                    "design_id": did,
                    "stage": "handoff_gate",
                    "fail_reasons": [
                        f"unpinned_gate:{g}" for g in pins.get("unpinned_gates") or []
                    ],
                    "reason_codes": [],
                    "unclassified_fail_reasons": [
                        f"unpinned_gate:{g}" for g in pins.get("unpinned_gates") or []
                    ],
                }
            )
    return records


def write_rejections(
    panel: dict[str, Any], path: Path, *, stage: str = "layer2_output_schema_pre_judge"
) -> int:
    """Write the rejection store declared by FLEET.toml [rejections]. Returns the count."""
    records = rejection_records(panel, stage=stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return len(records)


def _handoff_note(
    blocked: bool,
    pins: dict[str, Any],
    eligible: list,
    errors: dict[str, str] | None = None,
) -> str | None:
    if errors:
        return (
            f"handoff blocked: {len(errors)} design(s) raised during scoring and are "
            "absent from this panel: " + ", ".join(sorted(errors))
        )
    if blocked:
        return (
            "handoff blocked: "
            + ", ".join(pins.get("unpinned_gates") or ["unknown"])
            + " have unpinned inputs and were never evaluated"
        )
    if not eligible:
        return "No design cleared the hard gates; nothing is handed off."
    return None

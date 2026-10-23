"""Specificity margin + developability liability filters (pure CPU, Layer 2)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from contact_analysis import BINDER_CHAIN, assert_layout, load_chains

DEFAULT_MOTIFS = ["NG", "NS", "NT", "NH", "DG", "DS", "DT", r"N[^P][ST]"]
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
) -> dict[str, Any]:
    motifs = scan_motifs(sequence, motif_patterns)
    cys_count = sequence.count("C")
    unpaired_cys_fail = cys_count > 0
    ox_count = sum(sequence.count(r) for r in oxidation_residues)
    oxidation_fail = ox_count >= oxidation_threshold
    sap_note = "skipped_no_sap"
    sap_soft_fail = False

    hard_fail = bool(motifs) or unpaired_cys_fail or oxidation_fail
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
        "margin_status": "computed",
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
    if tier0.get("item_3_buried_anchor_contact_count", 0) != 0:
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
        and tier0.get("item_3_buried_anchor_contact_count", 0) == 0
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
        dev = row.get("liability_filters", {}).get("developability_score", 0.0)
        iptm = row.get("iptm") or -1e9
        return (-margin_key, -dev, -iptm)

    return sorted(rows, key=sort_key)


def build_panel_payload(
    bundle: dict[str, Any],
    *,
    campaign_id: str = "NYESO1-A0201-specificity",
    handoff_top_n: int = 3,
    api_contract_version: str = "v2026-03-01",
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
    handoff = ranked[:handoff_top_n]
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
        "handoff": {
            "top_n": handoff_top_n,
            "recipient": "BIO Physician",
            "designs": handoff,
        },
    }

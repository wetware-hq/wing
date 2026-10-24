"""Specificity margin: rank-average descriptors per peptide, then on-target rank − best-decoy rank."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Literal

Direction = Literal["higher", "lower"]

DEFAULT_DESCRIPTOR_STACK: tuple[str, ...] = (
    "complex_iplddt",
    "shape_complementarity",
    "plddt",
    "min_ipsae",
    "ipsae",
    "iptm",
    "pae_interaction",
)

# Field extractors for a scored row (layer-2 bundle block + optional metrics.json).
_EXTRACTORS: dict[str, tuple[Direction, Callable[[dict[str, Any]], float | None]]] = {
    "complex_iplddt": ("higher", lambda r: _num(r.get("complex_iplddt"))),
    "shape_complementarity": (
        "higher",
        lambda r: _num(r.get("shape_complementarity")),
    ),
    "plddt": ("higher", lambda r: _num(r.get("plddt"))),
    "min_ipsae": ("higher", lambda r: _num(r.get("min_ipsae"))),
    "ipsae": ("higher", lambda r: _num(r.get("ipsae"))),
    "iptm": ("higher", lambda r: _num(r.get("iptm"))),
    "pae_interaction": ("lower", lambda r: _num(r.get("pae_interaction"))),
}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
        return float(v)
    return None


def row_from_layer2_design(design_block: dict[str, Any]) -> dict[str, Any]:
    """Flatten orchestrator design record into descriptor row."""
    ipsae = design_block.get("ipsae") or {}
    metrics_iptm = ipsae.get("iptm")
    chain_d = (ipsae.get("chain_mean_plddt") or {}).get("D")
    min_ipsae = ipsae.get("min_ipsae_overall")
    pairs = ipsae.get("pairs") or {}
    cd = pairs.get("C|D") or pairs.get("D|C") or {}
    # Path A (specificity_scoring.peptide_binder_ipsae) defines the peptide-binder
    # descriptor as min(C->D, D->C); the pair record exposes that as "min_ipsae".
    ipsae_cd = cd.get("min_ipsae") if isinstance(cd, dict) else None
    item10 = design_block.get("item10_docking") or {}
    sc = item10.get("complementarity_contact_fraction_delta")
    prov = design_block.get("provenance") or {}
    return {
        "design_id": prov.get("design_id"),
        "job_id": prov.get("job_id"),
        "artifact_paths": prov.get("artifact_paths"),
        "pins": prov.get("pins"),
        "iptm": metrics_iptm,
        "plddt": chain_d,
        "min_ipsae": min_ipsae,
        "ipsae": ipsae_cd,
        "complex_iplddt": _read_metrics_field(design_block, "complex_iplddt"),
        "pae_interaction": _read_metrics_field(design_block, "min_interaction_pae"),
        "shape_complementarity": sc,
        "contact_site": design_block.get("contact_site"),
    }


def _read_metrics_field(design_block: dict[str, Any], key: str) -> float | None:
    """metrics.json is not embedded in bundle; caller may attach metrics_inline."""
    inline = design_block.get("metrics_inline") or {}
    return _num(inline.get(key))


# Fields read out of metrics.json. The cognate and the decoy refolds are
# produced by different pipelines and their metrics.json schemas differ, so
# record which of these were actually present rather than letting a missing one
# become a null descriptor downstream.
METRICS_FIELDS = ("complex_iplddt", "min_interaction_pae")


def attach_metrics_inline(design_block: dict[str, Any], metrics_path: Path | None) -> None:
    if not metrics_path or not metrics_path.is_file():
        design_block["metrics_inline_status"] = {
            "found": False,
            "path": str(metrics_path) if metrics_path else None,
            "missing_fields": list(METRICS_FIELDS),
        }
        return
    doc = json.loads(metrics_path.read_text())
    design_block["metrics_inline"] = doc
    design_block["metrics_inline_status"] = {
        "found": True,
        "path": str(metrics_path),
        "missing_fields": [f for f in METRICS_FIELDS if doc.get(f) is None],
    }


def average_rank(values: list[float | None], higher_is_better: bool) -> dict[int, float]:
    """Return rank (1 = best) for each index in values. Missing values rank last."""
    indexed = [(i, v) for i, v in enumerate(values)]
    present = [(i, v) for i, v in indexed if v is not None]
    missing = [i for i, v in indexed if v is None]
    if not present:
        return {i: float(len(values)) for i in range(len(values))}

    present.sort(key=lambda t: t[1], reverse=higher_is_better)
    ranks: dict[int, float] = {}
    # Tied values must share the MEAN of the ordinal positions they span. With
    # plain enumerate, ties were broken by list order, and the cognate is
    # inserted first by construction: a panel carrying no discriminating signal
    # whatsoever handed the cognate rank 1 on every descriptor and reported the
    # resulting margin as a pass. A tie must contribute exactly zero margin.
    i = 0
    while i < len(present):
        j = i
        while j + 1 < len(present) and present[j + 1][1] == present[i][1]:
            j += 1
        shared = (i + 1 + j + 1) / 2.0  # mean of the 1-based positions i..j
        for idx, _val in present[i : j + 1]:
            ranks[idx] = shared
        i = j + 1
    worst = float(len(values))
    for idx in missing:
        ranks[idx] = worst
    return ranks


def rank_average_score(
    rows: list[dict[str, Any]],
    stack: tuple[str, ...] = DEFAULT_DESCRIPTOR_STACK,
) -> list[dict[str, Any]]:
    """Add per-row descriptor values, per-descriptor ranks, and rank_average."""
    n = len(rows)
    per_desc_ranks: dict[str, list[float]] = {d: [0.0] * n for d in stack}
    for d in stack:
        direction, fn = _EXTRACTORS[d]
        vals = [fn(r) for r in rows]
        idx_ranks = average_rank(vals, higher_is_better=(direction == "higher"))
        for i in range(n):
            per_desc_ranks[d][i] = idx_ranks[i]
        for i, r in enumerate(rows):
            r.setdefault("descriptors", {})[d] = vals[i]
            r.setdefault("descriptor_ranks", {})[d] = idx_ranks[i]

    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        avg = sum(per_desc_ranks[d][i] for d in stack) / len(stack)
        r["rank_average"] = round(avg, 6)
        out.append(r)
    return out


# Below this many complete descriptors the rank average is no longer a
# meaningful aggregate, so the margin is withheld rather than reported thin.
MIN_EFFECTIVE_DESCRIPTORS = 3


def compute_specificity_margin(
    peptide_rows: list[dict[str, Any]],
    *,
    cognate_peptide_id: str,
    decoy_peptide_ids: list[str],
    stack: tuple[str, ...] = DEFAULT_DESCRIPTOR_STACK,
) -> dict[str, Any]:
    """Rank peptides within one survivor; margin = cognate rank − best decoy rank (lower rank is better)."""
    by_id = {r["peptide_id"]: r for r in peptide_rows}
    if cognate_peptide_id not in by_id:
        return {
            "status": "incomplete",
            "reason": f"missing cognate row {cognate_peptide_id}",
        }
    missing_decoys = [d for d in decoy_peptide_ids if d not in by_id]
    if missing_decoys:
        return {
            "status": "incomplete",
            "reason": "missing decoy rows",
            "missing_decoy_peptide_ids": missing_decoys,
            "panel_ready": False,
        }

    # Fail loud rather than ranking on a partially-missing descriptor stack: a
    # descriptor that is null for every peptide contributes a constant rank and
    # silently dilutes the margin instead of invalidating it.
    empty_descriptors = [
        d
        for d in stack
        if all(_EXTRACTORS[d][1](r) is None for r in peptide_rows)
    ]
    if empty_descriptors:
        return {
            "status": "incomplete",
            "reason": "descriptor(s) null for every peptide in the panel",
            "empty_descriptors": empty_descriptors,
            "descriptor_stack": list(stack),
            "panel_ready": False,
        }

    # A descriptor null for SOME peptides is more dangerous than one null for
    # all of them. average_rank places missing values last, so a descriptor that
    # is present for the cognate and absent for every decoy awards the cognate
    # the best rank on that descriptor by construction and manufactures apparent
    # specificity. Drop any descriptor with a null cell instead of ranking
    # around it, and say which and why.
    null_cells = {
        d: sorted(
            r["peptide_id"] for r in peptide_rows if _EXTRACTORS[d][1](r) is None
        )
        for d in stack
    }
    dropped = sorted(d for d, ids in null_cells.items() if ids)
    effective = tuple(d for d in stack if d not in dropped)
    if len(effective) < MIN_EFFECTIVE_DESCRIPTORS:
        return {
            "status": "incomplete",
            "reason": (
                f"only {len(effective)} of {len(stack)} descriptors are complete "
                f"across the panel; {MIN_EFFECTIVE_DESCRIPTORS} are required"
            ),
            "descriptor_stack": list(stack),
            "effective_descriptor_stack": list(effective),
            "excluded_descriptors": {d: null_cells[d] for d in dropped},
            "panel_ready": False,
        }

    ranked = rank_average_score(list(peptide_rows), stack=effective)
    id_to_rank = {r["peptide_id"]: r["rank_average"] for r in ranked}
    # Convert rank_average to ordinal rank among peptides (1 = best = lowest
    # rank_average). Ties must share the MEAN ordinal: breaking them by
    # peptide_id gave "cognate" the win alphabetically, so a panel carrying no
    # discriminating signal reported a negative (passing) margin.
    sorted_ids = sorted(id_to_rank.keys(), key=lambda k: (id_to_rank[k], k))
    ordinal: dict[str, float] = {}
    i = 0
    while i < len(sorted_ids):
        j = i
        while (
            j + 1 < len(sorted_ids)
            and id_to_rank[sorted_ids[j + 1]] == id_to_rank[sorted_ids[i]]
        ):
            j += 1
        shared = (i + 1 + j + 1) / 2.0
        for pid in sorted_ids[i : j + 1]:
            ordinal[pid] = shared
        i = j + 1

    on_target = ordinal[cognate_peptide_id]
    best_decoy = min(ordinal[d] for d in decoy_peptide_ids)
    margin = on_target - best_decoy

    return {
        # "computed" is reserved for a margin from the full declared stack. A
        # reduced stack still gives an unbiased number, but it is not the
        # endpoint the campaign declared, so it must not read as one.
        "status": "computed" if not dropped else "computed_reduced_stack",
        "ranking_rule": "rank_average",
        "descriptor_stack": list(stack),
        "effective_descriptor_stack": list(effective),
        "excluded_descriptors": {d: null_cells[d] for d in dropped},
        "on_target_peptide_id": cognate_peptide_id,
        "on_target_rank": on_target,
        "best_decoy_peptide_id": min(decoy_peptide_ids, key=lambda d: ordinal[d]),
        "best_decoy_rank": best_decoy,
        # Named rank_margin, not specificity_margin: this is an ordinal rank
        # difference on Path B's seven-descriptor stack, NOT the quantity
        # FLEET.toml [gates].hard gates at >= 0.15, which is on a different
        # scale and has the opposite sign convention. Sharing the name invited
        # a reader to compare the two numbers directly.
        "rank_margin": margin,
        "margin_scale": "ordinal_rank_difference",
        "peptide_rows": ranked,
        # Strictly less than zero: a margin of exactly 0 means the cognate
        # merely TIES the best decoy, which is no discrimination at all and
        # was being reported as a draft pass.
        "pass_in_silico_draft": margin < 0,
    }


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True)

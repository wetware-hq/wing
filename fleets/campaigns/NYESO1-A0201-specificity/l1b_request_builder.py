"""Build canonical L1B (decoy refold) request bodies — prediction API, fixed binder + peptide variant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# HLA-A*02:01 + b2m sequences verified in run-one request-legacy-submitted.json
HLA_A_SEQ = (
    "GSHSMRYFFTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEGPEYWDQETRNVKAQSQTDRVDLGTLRGYYNQSEAGSHT"
    "IQIMYGCDVGSDGRFLRGYRQDAYDGKDYIALNEDLRSWTAADMAAQITKRKWEAAHEAEQLRAYLDGTCVEWLRRYLENGKETLQRTDPPKTHM"
    "THHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAGDGTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWE"
)
B2M_SEQ = (
    "IQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEHSDLSFSKDWSFYLLYYTEFTPTEKDEYACRVNHVTLSQPKIVKWDRDM"
)

# targeted panel from parent FLEET.toml [[negative_design_panels]] recommended=true
TARGETED_PANEL = {
    "name": "targeted",
    "chain_A_marked": ["180-274", "56-61", "76-83", "137-148", "166-179"],
    "chain_B_marked": ["0-98"],
}


def _expand_ranges(ranges: list[str]) -> list[int]:
    out: list[int] = []
    for spec in ranges:
        if "-" in spec:
            a, b = spec.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(spec))
    return sorted(set(out))


def non_binding_residues_for_panel(panel: dict[str, Any]) -> dict[str, list[int]]:
    nb: dict[str, list[int]] = {}
    if "chain_A_marked" in panel:
        nb["A"] = _expand_ranges(panel["chain_A_marked"])
    if "chain_B_marked" in panel:
        nb["B"] = _expand_ranges(panel["chain_B_marked"])
    return nb


def build_predict_request(
    *,
    binder_sequence: str,
    peptide_sequence: str,
    negative_design_panel: str = "targeted",
    model: str = "boltz-2.1",
) -> dict[str, Any]:
    """POST https://api.boltz.bio/compute/v1/protein/predict (structure + binding, fixed sequences)."""
    if negative_design_panel != "targeted":
        raise ValueError("only targeted panel is encoded; override via manifest for other panels")
    nb = non_binding_residues_for_panel(TARGETED_PANEL)
    entities: list[dict[str, Any]] = [
        {"type": "protein", "chain_ids": ["A"], "value": HLA_A_SEQ},
        {"type": "protein", "chain_ids": ["B"], "value": B2M_SEQ},
        {
            "type": "protein",
            "chain_ids": ["C"],
            "value": peptide_sequence,
            "epitope_residues": list(range(9)),
        },
        {"type": "protein", "chain_ids": ["D"], "value": binder_sequence},
    ]
    # non_binding_residues apply to target chains A/B per run-one probe convention
    entities[0]["non_binding_residues"] = nb.get("A", [])
    entities[1]["non_binding_residues"] = nb.get("B", [])

    return {
        "model": model,
        "input": {
            "entities": entities,
        },
        "_meta": {
            "campaign": "NYESO1-A0201-specificity",
            "node": "L1B",
            "negative_design_panel": negative_design_panel,
            "api_contract_version": "v2026-03-01",
            "note": (
                "Prediction endpoint for decoy refold; design endpoint legacy shape is NOT used here. "
                "Verify body against live docs before spend."
            ),
        },
    }


def write_l1b_manifest(
    survivors: list[dict[str, Any]],
    peptides: list[dict[str, Any]],
    out_path: Path,
    *,
    negative_design_panel: str = "targeted",
) -> None:
    jobs: list[dict[str, Any]] = []
    for s in survivors:
        for p in peptides:
            seq = p.get("sequence")
            if not seq:
                continue
            jobs.append(
                {
                    "design_id": s["design_id"],
                    "peptide_id": p["peptide_id"],
                    "request": build_predict_request(
                        binder_sequence=s["binder_sequence"],
                        peptide_sequence=seq,
                        negative_design_panel=negative_design_panel,
                    ),
                }
            )
    out_path.write_text(json.dumps({"jobs": jobs}, indent=1, sort_keys=True))


def load_yaml_minimal(path: Path) -> dict[str, Any]:
    """Load decoy/survivor YAML without PyYAML (keys-only structure)."""
    try:
        import yaml  # type: ignore
    except ImportError:
        raise RuntimeError("PyYAML required to load panel YAML") from None
    return yaml.safe_load(path.read_text())

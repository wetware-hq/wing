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


def build_structure_and_binding_input(
    *,
    binder_sequence: str,
    peptide_sequence: str,
) -> dict[str, Any]:
    """Input body for POST /compute/v1/predictions/structure-and-binding (live API 2026-10-23).

    The prediction API rejects ``non_binding_residues`` / ``epitope_residues`` on entities.
    Negative-design intent for L1B is recorded in campaign manifest only until the predict
    API accepts the same annotations as design.
    """
    entities: list[dict[str, Any]] = [
        {"type": "protein", "chain_ids": ["A"], "value": HLA_A_SEQ},
        {"type": "protein", "chain_ids": ["B"], "value": B2M_SEQ},
        {"type": "protein", "chain_ids": ["C"], "value": peptide_sequence},
        {"type": "protein", "chain_ids": ["D"], "value": binder_sequence},
    ]
    return {
        "entities": entities,
        "binding": {"type": "protein_protein_binding", "binder_chain_ids": ["D"]},
        "num_samples": 1,
    }


def build_structure_and_binding_payload(
    *,
    binder_sequence: str,
    peptide_sequence: str,
    model: str = "boltz-2.1",
) -> dict[str, Any]:
    return {
        "model": model,
        "input": build_structure_and_binding_input(
            binder_sequence=binder_sequence,
            peptide_sequence=peptide_sequence,
        ),
    }


def build_predict_request(
    *,
    binder_sequence: str,
    peptide_sequence: str,
    negative_design_panel: str = "targeted",
    model: str = "boltz-2.1",
) -> dict[str, Any]:
    """Legacy manifest wrapper; wire payload uses structure-and-binding API."""
    del negative_design_panel  # manifest-only until predict API accepts annotations
    payload = build_structure_and_binding_payload(
        binder_sequence=binder_sequence,
        peptide_sequence=peptide_sequence,
        model=model,
    )
    payload["_meta"] = {
        "campaign": "NYESO1-A0201-specificity",
        "node": "L1B",
        "api_path": "/compute/v1/predictions/structure-and-binding",
        "api_contract_version": "v2026-03-01",
        "negative_design_panel_note": "targeted panel in FLEET; not sent on predict API (validation)",
    }
    return payload


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

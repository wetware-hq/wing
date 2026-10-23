"""Unit tests for specificity margin ranking (no Boltz / bindi required)."""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "fleets" / "campaigns" / "NYESO1-A0201-specificity"


def _load_sm():
    path = SPEC / "specificity_margin.py"
    spec = importlib.util.spec_from_file_location("specificity_margin", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["specificity_margin"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_average_rank_higher_is_better():
    sm = _load_sm()
    ranks = sm.average_rank([0.2, 0.9, 0.5], higher_is_better=True)
    assert ranks[1] == 1.0
    assert ranks[2] == 2.0
    assert ranks[0] == 3.0


def test_specificity_margin_negative_when_cognate_wins():
    sm = _load_sm()
    rows = [
        {"peptide_id": "cognate", "iptm": 0.95, "plddt": 90.0, "min_ipsae": 0.7, "ipsae": 0.6,
         "complex_iplddt": 0.9, "shape_complementarity": 0.2, "pae_interaction": 1.0},
        {"peptide_id": "decoy_a", "iptm": 0.40, "plddt": 70.0, "min_ipsae": 0.1, "ipsae": 0.05,
         "complex_iplddt": 0.5, "shape_complementarity": 0.05, "pae_interaction": 8.0},
        {"peptide_id": "decoy_b", "iptm": 0.55, "plddt": 75.0, "min_ipsae": 0.2, "ipsae": 0.1,
         "complex_iplddt": 0.55, "shape_complementarity": 0.08, "pae_interaction": 6.0},
    ]
    out = sm.compute_specificity_margin(
        rows,
        cognate_peptide_id="cognate",
        decoy_peptide_ids=["decoy_a", "decoy_b"],
    )
    assert out["status"] == "computed"
    assert out["on_target_rank"] == 1
    assert out["specificity_margin"] <= 0
    assert out["pass_in_silico_draft"] is True


def test_incomplete_without_decoys():
    sm = _load_sm()
    rows = [{"peptide_id": "cognate", "iptm": 0.9, "plddt": 80.0, "min_ipsae": 0.5, "ipsae": 0.4,
             "complex_iplddt": 0.8, "shape_complementarity": 0.1, "pae_interaction": 2.0}]
    out = sm.compute_specificity_margin(
        rows,
        cognate_peptide_id="cognate",
        decoy_peptide_ids=["decoy_a"],
    )
    assert out["status"] == "incomplete"

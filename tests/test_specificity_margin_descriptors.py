"""Guards for the descriptor plumbing in the specificity margin reader (Path B)."""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parents[1] / "fleets/campaigns/NYESO1-A0201-specificity"
if str(CAMPAIGN) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN))

import specificity_margin as sm  # noqa: E402


def _design_block(min_ipsae_cd: float | None) -> dict:
    return {
        "provenance": {"design_id": "pres_test", "job_id": "job_test"},
        "ipsae": {
            "iptm": 0.8,
            "chain_mean_plddt": {"D": 86.0},
            "min_ipsae_overall": min_ipsae_cd,
            "pairs": {
                "C|D": {
                    "min_ipsae": min_ipsae_cd,
                    "ipsae_C_to_D": 0.9,
                    "ipsae_D_to_C": min_ipsae_cd,
                }
            },
        },
        "item10_docking": {"complementarity_contact_fraction_delta": 0.1},
    }


def _panel(values: list[float | None]) -> list[dict]:
    ids = ["cognate_X"] + [f"decoy_{i}" for i in range(len(values) - 1)]
    rows = []
    for i, (pid, val) in enumerate(zip(ids, values)):
        row = sm.row_from_layer2_design(_design_block(val))
        row["peptide_id"] = pid
        row["complex_iplddt"] = 0.9 - i * 0.1
        row["pae_interaction"] = 5.0 + i
        rows.append(row)
    return rows


def test_ipsae_descriptor_reads_min_ipsae_from_pair_record():
    """Path A scores the peptide-binder pair as min(C->D, D->C); Path B must read the same key."""
    row = sm.row_from_layer2_design(_design_block(0.0654306831581959))
    assert row["ipsae"] == 0.0654306831581959
    assert row["min_ipsae"] == 0.0654306831581959


def test_margin_is_incomplete_when_a_descriptor_is_null_for_every_peptide():
    """A descriptor missing across the whole panel must invalidate the margin, not dilute it."""
    out = sm.compute_specificity_margin(
        _panel([None, None, None]),
        cognate_peptide_id="cognate_X",
        decoy_peptide_ids=["decoy_0", "decoy_1"],
    )
    assert out["status"] == "incomplete"
    assert out["panel_ready"] is False
    assert "ipsae" in out["empty_descriptors"]
    assert "min_ipsae" in out["empty_descriptors"]
    assert "rank_margin" not in out
    assert "pass_in_silico_draft" not in out


def test_margin_computes_when_the_stack_is_populated():
    out = sm.compute_specificity_margin(
        _panel([0.30, 0.10, 0.05]),
        cognate_peptide_id="cognate_X",
        decoy_peptide_ids=["decoy_0", "decoy_1"],
    )
    assert out["status"] == "computed"
    assert out["on_target_rank"] == 1
    assert out["rank_margin"] < 0
    assert out["pass_in_silico_draft"] is True

"""An input that was never measured must not read as a passing value.

Zero buried anchor contacts is the PASSING value for that gate, and an empty
decoy panel subset still yields a real-looking margin. Both defaulted to the
benign reading, so a design nobody measured cleared the hard gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_ONE = Path(__file__).resolve().parents[1] / "fleets/campaigns/NYESO1-A0201/run-one"
if str(RUN_ONE) not in sys.path:
    sys.path.insert(0, str(RUN_ONE))

import specificity_scoring as ss  # noqa: E402

PASSING_SPEC = {"specificity_margin": 0.4, "margin_status": "computed"}
PASSING_LIAB = {"pass": True, "developability_score": 1.0}
PASSING_IPSAE = {"iptm": 0.9, "chain_mean_plddt": {"D": 90.0}}


def _gates(*, spec=None, tier0=None, liab=None):
    return ss.evaluate_gates(
        spec if spec is not None else dict(PASSING_SPEC),
        liab if liab is not None else dict(PASSING_LIAB),
        tier0 if tier0 is not None else {"item_3_buried_anchor_contact_count": 0},
        dict(PASSING_IPSAE),
    )


def test_an_otherwise_perfect_design_passes():
    g = _gates()
    assert g["hard_pass"] is True
    assert g["fail_reasons"] == []


def test_an_absent_buried_anchor_count_fails_rather_than_reading_as_zero():
    # tier0 analysis raised, so the key is simply not there. Zero is the
    # passing value, so defaulting to it is the dangerous direction.
    g = _gates(tier0={})
    assert g["hard_pass"] is False
    assert "buried_anchor_contacts:unmeasured" in g["fail_reasons"]


def test_a_nonzero_buried_anchor_count_still_fails_as_nonzero():
    g = _gates(tier0={"item_3_buried_anchor_contact_count": 3})
    assert g["hard_pass"] is False
    assert "buried_anchor_contacts:nonzero" in g["fail_reasons"]


def test_a_margin_from_a_partial_decoy_panel_fails_the_gate():
    spec = {
        "specificity_margin": 0.4,
        "margin_status": "partial_decoy_panel",
        "decoys_missing": ["d3", "d7"],
    }
    g = _gates(spec=spec)
    assert g["hard_pass"] is False
    assert "decoy_panel:incomplete(2 unscored)" in g["fail_reasons"]


# --------------------------------------------------------------------------
# compute_margin must report decoy coverage, not quietly score the subset.
# --------------------------------------------------------------------------


def test_a_fully_scored_panel_is_computed():
    m = ss.compute_margin(0.9, {"d1": 0.2, "d2": 0.3})
    assert m["margin_status"] == "computed"
    assert m["decoy_panel_size"] == 2
    assert m["decoys_scored"] == 2
    assert m["decoys_missing"] == []
    assert m["specificity_margin"] == 0.6


def test_a_partly_scored_panel_is_not_called_computed():
    # The best decoy may well be one of the two that failed to score, so the
    # margin against the survivors is a real number against a wrong denominator.
    m = ss.compute_margin(0.9, {"d1": 0.2, "d2": None, "d3": None})
    assert m["margin_status"] == "partial_decoy_panel"
    assert m["decoys_scored"] == 1
    assert m["decoys_missing"] == ["d2", "d3"]
    # The number is still reported, for audit; it just may not be gated on.
    assert m["specificity_margin"] == 0.7


def test_a_wholly_unscored_panel_stays_pending():
    m = ss.compute_margin(0.9, {"d1": None})
    assert m["margin_status"] == "pending_l1b"
    assert m["specificity_margin"] is None

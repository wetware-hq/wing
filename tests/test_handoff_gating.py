"""The T1 handoff must gate on the verdict, not on rank.

Before this, both paths handed off the top N by rank. Ranking is total: the best
of ten failures still ranks first, so a panel in which nothing passed still
produced a populated handoff. An empty handoff is a valid, meaningful result.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ONE = ROOT / "fleets/campaigns/NYESO1-A0201/run-one"
CAMPAIGN = ROOT / "fleets/campaigns/NYESO1-A0201-specificity"
for _p in (RUN_ONE, CAMPAIGN):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import specificity_scoring as ss  # noqa: E402
import specificity_orchestrator as so  # noqa: E402


# --------------------------------------------------------------------------
# Path A: build_panel_payload gates on gates.hard_pass
# --------------------------------------------------------------------------


def _bundle(*designs: tuple[str, bool, float]) -> dict:
    return {
        "pins": {},
        "designs": {
            design_id: {
                "binder_sequence": "EVQLVESGGG",
                "provenance": {"design_id": design_id},
                "iptm": 0.8,
                "ipsae": {"iptm": 0.8, "chain_mean_plddt": {"D": 85.0}},
                "liability_filters": {"developability_score": 0.5},
                "specificity": {"specificity_margin": margin},
                "gates": {
                    "hard_pass": hard_pass,
                    "fail_reasons": [] if hard_pass else ["developability:liability_motifs"],
                },
            }
            for design_id, hard_pass, margin in designs
        },
    }


def test_path_a_hands_off_nothing_when_no_design_clears_the_hard_gates():
    payload = ss.build_panel_payload(
        _bundle(("d_best", False, 0.09), ("d_mid", False, 0.02), ("d_worst", False, -0.3))
    )
    handoff = payload["handoff"]
    assert handoff["designs"] == []
    assert handoff["eligible_count"] == 0
    assert handoff["gate"] == "gates.hard_pass"
    assert "nothing is handed off" in handoff["note"]


def test_path_a_records_every_excluded_design_with_its_reason():
    payload = ss.build_panel_payload(
        _bundle(("d_pass", True, 0.4), ("d_fail", False, 0.9))
    )
    excluded = payload["handoff"]["excluded"]
    assert [e["design_id"] for e in excluded] == ["d_fail"]
    assert excluded[0]["fail_reasons"] == ["developability:liability_motifs"]
    # d_fail has the better margin so it ranks first, yet it is not handed off.
    assert payload["designs"][0]["design_id"] == "d_fail"
    assert [d["design_id"] for d in payload["handoff"]["designs"]] == ["d_pass"]


def test_path_a_treats_a_design_with_no_gates_block_as_ineligible():
    bundle = _bundle(("d_ungated", True, 0.4))
    del bundle["designs"]["d_ungated"]["gates"]
    payload = ss.build_panel_payload(bundle)
    assert payload["handoff"]["designs"] == []
    assert payload["handoff"]["excluded"][0]["fail_reasons"] == ["gates:absent"]


# --------------------------------------------------------------------------
# Path B: transport_payload gates on margin.pass_in_silico_draft, and is
# blocked outright while a declared gate has unpinned inputs.
# --------------------------------------------------------------------------


def _ranked(*designs: tuple[str, str, bool, float]) -> dict:
    return {
        "campaign_id": "NYESO1-A0201-specificity",
        "manifest_hash": "deadbeef",
        "designs": [
            {
                "design_id": design_id,
                "binder_sequence": "EVQLVESGGG",
                "margin": {
                    "status": status,
                    "pass_in_silico_draft": passed,
                    "specificity_margin": margin,
                    "on_target_rank": 1,
                    "best_decoy_rank": 2,
                    "peptide_rows": [{"contact_site": "A"}],
                },
            }
            for design_id, status, passed, margin in designs
        ],
    }


PINNED = {"all_pinned": True, "unpinned_gates": [], "findings": []}
UNPINNED = {
    "all_pinned": False,
    "unpinned_gates": ["calibration", "species_cross_reactivity"],
    "findings": [{"gate": "calibration", "detail": "anchors deferred"}],
}


def test_path_b_computed_but_failing_is_not_handed_off():
    payload = so.transport_payload(
        _ranked(("d_fail", "computed", False, 0.4)), config_pins_report=PINNED
    )
    assert payload["top_designs_by_specificity_margin"] == []
    assert payload["eligible_count"] == 0
    assert payload["gate"] == "margin.pass_in_silico_draft"
    assert payload["excluded_designs"][0]["reason"] == "cognate does not outrank every decoy"


def test_path_b_hands_off_a_passing_design_when_the_gates_are_pinned():
    payload = so.transport_payload(
        _ranked(("d_pass", "computed", True, -0.4)), config_pins_report=PINNED
    )
    assert [d["design_id"] for d in payload["top_designs_by_specificity_margin"]] == ["d_pass"]
    assert payload["handoff_blocked_by_unpinned_gates"] is False
    assert payload["handoff_block_reason"] is None


def test_path_b_blocks_the_handoff_while_a_declared_gate_is_unpinned():
    payload = so.transport_payload(
        _ranked(("d_pass", "computed", True, -0.4)), config_pins_report=UNPINNED
    )
    # The design is still eligible; it just cannot be handed off yet, and the
    # payload says why rather than reporting an empty panel.
    assert payload["eligible_count"] == 1
    assert payload["top_designs_by_specificity_margin"] == []
    assert payload["handoff_blocked_by_unpinned_gates"] is True
    assert "calibration" in payload["handoff_block_reason"]


def test_path_b_carries_an_incomplete_margin_through_with_its_reason():
    ranked = _ranked(("d_incomplete", "incomplete", False, None))
    ranked["designs"][0]["margin"]["reason"] = "descriptor(s) null for every peptide"
    payload = so.transport_payload(ranked, config_pins_report=PINNED)
    assert payload["excluded_designs"][0]["reason"] == "descriptor(s) null for every peptide"

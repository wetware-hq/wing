"""The design request must carry the declared targeting, not the whole peptide.

Run one declared hotspots on P4-P8 and staged three non_binding panels, then
submitted epitope_residues=[0..8] and no non_binding_residues. The failure mode
is the same as test_content_address_honesty and test_liability_declared_gates:
the spec declared something the wire never got. These tests pin the builder
output so that cannot happen again silently.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "fleets/campaigns/NYESO1-A0201"
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))


def _load():
    path = PARENT / "l1a_request_builder.py"
    spec = importlib.util.spec_from_file_location("l1a_request_builder", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["l1a_request_builder"] = mod
    spec.loader.exec_module(mod)
    return mod


b = _load()


def test_epitope_is_narrowed_to_p4_through_p8_as_0based_api_indices():
    assert b.EPITOPE_API_0BASED == (3, 4, 5, 6, 7)
    assert b.EPITOPE_AUTHOR_1BASED == (4, 5, 6, 7, 8)
    assert b.epitope_residues_api() == [3, 4, 5, 6, 7]


def test_indexing_conversion_is_author_minus_one():
    # Prove the convention the builder encodes: API = author - 1.
    for author, api in zip(b.EPITOPE_AUTHOR_1BASED, b.EPITOPE_API_0BASED):
        assert api == author - 1
    for author, api in zip(
        b.PEPTIDE_NON_BINDING_AUTHOR_1BASED, b.PEPTIDE_NON_BINDING_API_0BASED
    ):
        assert api == author - 1


def test_legacy_request_body_carries_narrowed_epitope():
    body = b.build_legacy_design_request(panel_name="targeted", num_proteins=10)
    assert body["target"]["epitope_residues"] == {"C": [3, 4, 5, 6, 7]}
    # Must not silently reintroduce the whole peptide.
    assert body["target"]["epitope_residues"]["C"] != list(range(9))


def test_legacy_request_body_carries_targeted_non_binding_panel():
    body = b.build_legacy_design_request(panel_name="targeted", num_proteins=10)
    nb = body["target"]["non_binding_residues"]
    # Targeted panel: alpha-3 + distal helix segments + all of B + peptide anchors.
    assert set(nb) == {"A", "B", "C"}
    assert nb["A"][0] == 56 and nb["A"][-1] == 274
    assert len(nb["A"]) == 135
    assert nb["B"] == list(range(99))
    assert nb["C"] == [0, 1, 8]


def test_all_three_panels_reach_the_request_body():
    """Each panel is well-specified in FLEET.toml; each must be buildable."""
    expected_A = {
        "conservative": 95,
        "targeted": 135,
        "aggressive": 166,
    }
    for name, n_a in expected_A.items():
        body = b.build_legacy_design_request(panel_name=name, num_proteins=10)
        nb = body["target"]["non_binding_residues"]
        assert len(nb["A"]) == n_a, name
        assert nb["B"] == list(range(99)), name
        assert nb["C"] == [0, 1, 8], name
        assert body["target"]["epitope_residues"]["C"] == [3, 4, 5, 6, 7], name


def test_default_panel_is_the_signed_targeted_one():
    assert b.DEFAULT_PANEL == "targeted"
    body = b.build_legacy_design_request(num_proteins=10)
    # Distinguisher: targeted marks 56-61 and 76-83 separately, so 62..75 free.
    a = set(body["target"]["non_binding_residues"]["A"])
    assert 56 in a and 61 in a
    assert 62 not in a and 75 not in a
    assert 65 not in a  # R65 of the restriction triad stays free under targeted


def test_request_shape_is_legacy_not_type_binder():
    body = b.build_legacy_design_request(num_proteins=10)
    assert "type" not in body  # top-level type:"binder" was rejected live
    assert "binder_specification" in body
    assert body["target"]["type"] == "no_template"
    assert body["num_proteins"] == 10


def test_fleet_toml_epitope_matches_the_builder():
    """Spec and builder cannot drift apart the way run one did."""
    fleet = b.load_fleet()
    assert fleet["target"]["chain_C"]["epitope_residues"] == b.epitope_residues_api()
    rationale = fleet["target"]["chain_C"]["epitope_rationale"]
    assert rationale["chosen_api_0based"] == b.epitope_residues_api()
    assert rationale["peptide_non_binding_api_0based"] == list(
        b.PEPTIDE_NON_BINDING_API_0BASED
    )


def test_pre_registered_readouts_are_report_only():
    fleet = b.load_fleet()
    pr = fleet["pre_registered_readouts"]
    assert pr["gate"] is False
    burial = pr["peptide_burial_fraction"]
    assert burial["control_distribution_min"] == 0.0
    assert burial["control_distribution_max"] == 0.419
    assert "NONE" in burial["threshold"]
    hot = pr["hotspot_contact_fraction"]
    assert "215" in hot["issue"]
    assert "honour" in hot["purpose"].lower() or "honor" in hot["purpose"].lower()
    assert "NONE" in hot["threshold"]


def test_p3_is_not_silently_added_to_either_set():
    """P3 is partly occluded, not shown buried; inventing a status would be wrong."""
    body = b.build_legacy_design_request(num_proteins=10)
    assert 2 not in body["target"]["epitope_residues"]["C"]  # author P3 -> API 2
    assert 2 not in body["target"]["non_binding_residues"]["C"]

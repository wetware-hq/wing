"""The declared content address must not name an input the pipeline never sets.

FLEET.toml declared `seed` as a component of content_address. No seed is sent to
the prediction API and none is recorded, so the address pinned nothing about the
prediction while claiming to. On 2026-10-24 a resubmit of all 100 decoy refolds
on identical inputs reproduced none of them, and every component of the address
was unchanged, as was the published hash.

Same failure mode as tests/test_liability_declared_gates.py: the spec declared
something the code does not do, and nothing failed loudly.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "fleets/campaigns/NYESO1-A0201-specificity"
PARENT = ROOT / "fleets/campaigns/NYESO1-A0201"
FLEET = CAMPAIGN / "FLEET.toml"
PARENT_FLEET = PARENT / "FLEET.toml"
if str(CAMPAIGN) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fleet(path: Path = FLEET) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


# Components the request builder and runner genuinely set or pin. A component
# added to content_address that is not in here has to be wired first.
SETTABLE = {
    "api_version",
    "config_hash",
    "target_hash",
    "bindi_wheel_sha256",
    "base_image_digest",
}


def test_content_address_names_no_component_the_pipeline_does_not_set():
    for path in (FLEET, PARENT_FLEET):
        declared = set(_fleet(path)["provenance"]["content_address"])
        unsettable = declared - SETTABLE
        assert not unsettable, (
            f"{path.name} content_address names {sorted(unsettable)}, which the "
            "pipeline never sets or records"
        )


def test_seed_is_not_claimed_anywhere_in_a_content_address():
    # The specific false component this test exists for.
    for path in (FLEET, PARENT_FLEET):
        assert "seed" not in _fleet(path)["provenance"]["content_address"]


def test_no_seed_is_actually_sent_or_recorded():
    # If a seed is ever wired up, this fails and the claim above may be restored.
    builder = (CAMPAIGN / "l1b_request_builder.py").read_text()
    runner = (CAMPAIGN / "l1b_runner.py").read_text()
    assert "seed" not in builder.lower()
    assert "seed" not in runner.lower()


def test_the_address_declares_that_it_does_not_cover_predictions():
    prov = _fleet()["provenance"]
    assert prov["artifacts_reproducible_from_address"] is False
    assert prov["content_address_scope"] == "configuration_and_environment_only"
    assert "prediction output" in prov["content_address_excludes"]


def test_stochasticity_is_declared_before_the_gate_is_trusted():
    fleet = _fleet()
    st = fleet["stochasticity"]
    assert st["seeded"] is False
    assert st["seed_recorded"] is False
    assert st["single_draw_reproduces"] is False
    # Declared ahead of [gates] in the file, so a reader meets it first.
    text = FLEET.read_text()
    assert text.index("[stochasticity]") < text.index("[gates]")


def test_the_measured_dispersion_is_recorded_beside_the_threshold():
    d = _fleet()["stochasticity"]["specificity_margin_dispersion"]
    assert d["n_designs"] == 10
    assert d["n_runs"] == 2
    assert d["mean_abs_difference"] == 0.0637
    assert d["max_abs_difference"] == 0.1174
    assert d["std_dev"] == 0.0725
    assert d["gate_threshold"] == 0.15


def test_the_gate_itself_keeps_anchors_and_liability_and_retires_015():
    # OD-11 retires specificity_margin >= 0.15 as objective; other hard gates stay.
    hard = _fleet()["gates"]["hard"]
    assert "specificity_margin >= 0.15" not in hard
    assert "buried_anchor_contacts == 0" in hard
    assert "liability_filters.pass" in hard
    assert _fleet()["gates"]["retired_from_hard"] == "specificity_margin >= 0.15"
    assert _fleet()["gates"]["retired_by"] == "OD-11"


def test_od5_is_recorded_with_three_options():
    ods = {o["id"]: o for o in _fleet()["open_decisions"]}
    assert "OD-5" in ods
    assert len(ods["OD-5"]["options"]) == 3


def test_the_published_hash_field_says_what_it_hashes():
    # Published as "manifest_hash", it read as an address of the artifacts; it
    # only ever hashed two config files.
    so = _load("specificity_orchestrator", CAMPAIGN / "specificity_orchestrator.py")
    assert hasattr(so, "_config_manifest_hash")
    assert not hasattr(so, "_manifest_hash")
    payload = so.transport_payload(
        {"designs": [], "campaign_id": "x", "config_manifest_hash": "y"},
        config_pins_report={"all_pinned": True, "unpinned_gates": []},
    )
    assert payload["config_manifest_hash"] == "y"
    assert payload["predictions_reproducible"] is False
    # The bare name is gone, so no consumer can keep reading it as an artifact address.
    assert "manifest_hash" not in payload


# --------------------------------------------------------------------------
# 2026-10-24, second measurement: the seed option in OD-5 was tested directly.
# Pinning the seed narrows the dispersion ~197-fold and still does not make a
# prediction reproduce. Both conditions must stay on the record, each labelled,
# and OD-5 must not read as though seeding were an untried idea.
# --------------------------------------------------------------------------


def test_both_dispersion_conditions_are_labelled():
    st = _fleet()["stochasticity"]
    unseeded = st["specificity_margin_dispersion"]
    seeded = st["seeded_dispersion"]
    # A reader must be able to tell which condition produced which number.
    assert "unseeded" in unseeded["condition"]
    assert "20261024" in seeded["condition"]
    assert unseeded["n_runs"] == 2
    assert seeded["n_runs"] == 2
    # Declared before the gate, like the unseeded figures.
    text = FLEET.read_text()
    assert text.index("[stochasticity.seeded_dispersion]") < text.index("[gates]")


def test_the_seeded_dispersion_numbers_are_recorded():
    d = _fleet()["stochasticity"]["seeded_dispersion"]
    assert d["margin_run_1"] == 0.150682
    assert d["margin_run_2"] == 0.150285
    assert d["abs_difference"] == 0.000397
    assert d["unseeded_abs_difference_same_design"] == 0.078112
    assert d["gate_threshold"] == 0.15
    # The residual exceeds one arm's headroom above the bar. That is the finding.
    assert d["abs_difference"] > d["headroom_run_2"]
    assert d["structures_reproduced"] == "5 of 10"


def test_the_seed_option_reports_that_it_was_tested_and_is_insufficient():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-5"]
    seed_option = next(o for o in od["options"] if o.startswith("pin and record a seed"))
    assert "TESTED" in seed_option
    # It must not still claim seeding makes runs reproducible.
    assert "makes runs reproducible" not in seed_option
    assert "does NOT make predictions identical" in seed_option
    assert "evidence_seeded" in od


def test_seeding_is_still_not_implemented_after_od5_auto_resolve():
    # Auto-resolution chose the OD-11 unseeded sign-test; it did NOT adopt
    # seeding. The builder must still send no sampler options.
    src = (CAMPAIGN / "l1b_request_builder.py").read_text()
    assert "model_options" not in src
    assert "seed" not in src
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-5"]
    assert od["status"] == "decided"
    assert od["resolution_mode"] == "auto_heuristic"
    assert "seeding is NOT implemented" in od["not_implemented"]
    assert "NOT adopted" in od["resolution"] or "not adopted" in od["resolution"]


# --------------------------------------------------------------------------
# 2026-10-27: OD-9 / OD-10 / OD-11 — Finding 0 protocol; geometric objective;
# demoted margin; arms reconciled. No spend authorised.
# --------------------------------------------------------------------------


def test_od9_path_a_uses_prediction_endpoint_only():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-9"]
    assert od["status"] == "decided"
    assert od["owner"] == "Campaign approver"
    assert "prediction" in od["resolution"].lower()
    assert "sab_pred_" in od["resolution"]
    assert "NOT a Path A margin input" in od["resolution"]
    # Protocol decided; wiring not yet done — Arm 0 of OD-10.
    assert "NOT YET WIRED" in od["implementation_status"]


def test_od11_retires_015_and_sets_geometric_objective():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-11"]
    assert od["status"] == "decided"
    assert od["owner"] == "Campaign approver"
    assert od["retired_threshold"] == "specificity_margin >= 0.15"
    assert "uncalibrated" in od["retired_reason"]
    assert "Finding 0" in od["retired_reason"]
    obj = _fleet()["objective"]
    assert obj["primary"] == "geometry"
    assert obj["geometric_ceiling"] == 0.4666
    assert obj["degeneracy_floor_status"] == "UNSET"
    assert obj["degeneracy_floor_control_engaging_n"] == 5
    assert obj["margin_role"] == "demoted"
    assert obj["margin_N"] == 10
    assert obj["margin_criterion"] == "central_tendency"
    assert obj["unlinked"] is True
    assert obj["disagreement_store"] == "artifacts/disagreements.jsonl"
    # Other hard gates not weakened.
    hard = _fleet()["gates"]["hard"]
    assert "buried_anchor_contacts == 0" in hard
    assert "liability_filters.pass" in hard
    assert "specificity_margin >= 0.15" not in hard
    soft = _fleet()["gates"]["soft"]
    assert "iptm >= 0.60" in soft
    assert "chain_D_plddt >= 80" in soft


def test_od11_degeneracy_floor_rule_is_pre_registered_not_invented():
    obj = _fleet()["objective"]
    assert obj["degeneracy_floor_status"] == "UNSET"
    assert "n=5" in obj["degeneracy_floor_why_unset"] or "n=5" in obj["degeneracy_floor_why_unset"].lower() or "n=5" in str(obj["degeneracy_floor_control_engaging_n"])
    assert "59" in obj["degeneracy_floor_derivation_rule"]
    assert "min(buried_vs_peptide_A2)" in obj["degeneracy_floor_derivation_rule"]
    # Control distribution recorded in full; engaging min is a fact, not a floor.
    dist = obj["degeneracy_floor_control_buried_vs_peptide_A2"]
    assert len(dist) == 13
    assert dist.count(0.0) == 8
    assert obj["degeneracy_floor_control_engaging_min"] == 217.4968723639522
    assert obj["degeneracy_floor_control_engaging_max"] == 310.02789921366


def test_od10_reconciled_to_geometric_objective():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-10"]
    assert od["status"] == "open"
    assert od["owner"] == "Campaign approver"
    assert od["reconciled_by"] == "OD-11"
    assert "0.4666" in od["objective"]
    assert "peptide_burial_fraction" in od["objective"]
    assert "SUPERSEDED" in od["objective"]
    # Retired cut lives only in the superseded record, not as the active objective.
    assert "specificity_margin >= 0.15" in od["prior_objective_superseded"]
    assert "retired as objective" in od["prior_objective_superseded"].lower() or "Superseded by OD-11" in od["prior_objective_superseded"]


def test_od10_names_kill_conditions_arms_and_decision_rule():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-10"]
    kills = od["kill_conditions"]
    for prefix in (
        "K1_FINDING0",
        "K2_HONOUR",
        "K3_BURIAL_STRATEGY",
        "K4_SCAFFOLD",
        "K5_VOLUME",
        "K6_UNPINNED_HANDOFF",
    ):
        assert any(k.startswith(prefix) for k in kills), prefix
    # K3 must be named as SUPERSEDED, not silently dropped.
    k3 = next(k for k in kills if k.startswith("K3_BURIAL_STRATEGY"))
    assert "SUPERSEDED" in k3
    assert od["arm_a_name"] == "ARM_A_DISAGREEMENT_SERIES"
    assert od["arm_a_prior_name"] == "ARM_A_BURIAL_MARGIN_COUPLING"
    assert od["arm_c_name"] == "ARM_C_SCAFFOLD_FOOTPRINT"
    assert "Arm 0 first" in od["decision_rule"][0]
    assert any("BURIAL_GEOMETRIC_CEILING" in p for p in od["pre_registered"])
    assert any("DEGENERACY_FLOOR_CONTROL" in p for p in od["pre_registered"])
    assert "Arms 0/A/C/D not authorised and not implemented" in od["status_note"]
    assert "Arm B COMPLETED" in od["status_note"]
    assert "SEQUENCE_READ" in od["status_note"]


def test_od10_update_existing_not_new_campaign_directory():
    # Preference: UPDATE existing >> write new. Plan lives on this campaign.
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-10"]
    assert "UPDATE this campaign" in od["update_vs_new"]
    clearing_dirs = list((ROOT / "fleets/campaigns").glob("*clear*"))
    assert clearing_dirs == []


def test_parent_scaffold_arm_is_staged_not_default():
    parent = _fleet(PARENT_FLEET)
    assert parent["binder"]["modality"] == "custom_protein"
    assert parent["binder"]["length_range"] == "60..100"
    staged = parent["binder"]["scaffold_arm_od10"]
    assert staged["status"] == "staged_not_default"
    assert staged["default_modality_unchanged"] is True
    assert staged["boltz_curated_blocked"] is True


def test_od5_auto_resolved_merged_with_od7():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-5"]
    assert od["status"] == "decided"
    assert od["resolution_mode"] == "auto_heuristic"
    assert od["merged_with"] == "OD-7"
    assert len(od["options"]) == 3
    assert "od11_interaction" in od
    assert "RETIRED" in od["od11_interaction"] or "retired" in od["od11_interaction"]
    assert "reopen_trigger" in od
    assert od["owner"] == "Campaign approver"


# --------------------------------------------------------------------------
# 2026-10-27: ROI pass — auto-resolve bottom 80% of OPEN; OD-10 remains.
# --------------------------------------------------------------------------


def test_decision_roi_definition_and_remaining_open():
    roi = _fleet()["decision_roi"]
    assert "blockage / effort_cost" in roi["definition"] or "blockage / effort_cost" in roi["definition"].replace(" ", "")
    assert "blockage" in roi["definition"] and "effort_cost" in roi["definition"]
    assert roi["n_open_scored"] == 4
    assert roi["n_auto_resolved"] == 3
    assert roi["n_kept_open"] == 1
    assert roi["remaining_open"] == ["OD-10"]
    assert "OD-4" in roi["deferred_not_in_resolve_set"]
    scores = {s["id"]: s for s in roi["scores"]}
    assert scores["OD-10"]["roi"] == 5.00
    assert scores["OD-10"]["auto_resolved"] is False
    assert scores["OD-7"]["roi"] == 3.00
    assert scores["OD-7"]["auto_resolved"] is True
    assert scores["OD-1"]["roi"] == 2.00
    assert scores["OD-1"]["auto_resolved"] is True
    assert scores["OD-5"]["roi"] == 2.00
    assert scores["OD-5"]["auto_resolved"] is True
    # Rank descending by ROI.
    ordered = sorted(roi["scores"], key=lambda s: (-s["roi"], s["rank"]))
    assert [s["id"] for s in ordered] == ["OD-10", "OD-7", "OD-1", "OD-5"]


def test_od1_auto_resolves_and_supersedes_provisional_gates():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-1"]
    assert od["status"] == "decided"
    assert od["resolution_mode"] == "auto_heuristic"
    assert od["owner"] == "Campaign approver"
    assert "margin >= 0.15" in od["prior_provisional_gates"]
    assert od["provisional_gates_superseded_by"] == "OD-11"
    assert "margin >= 0.15" not in od["provisional_gates"]
    assert "buried_anchor_contacts == 0" in od["provisional_gates"]
    assert "Boltz-native" in od["resolution"]
    assert "reopen_trigger" in od
    # Hard gates still match OD-11 (no weakening).
    hard = _fleet()["gates"]["hard"]
    assert "specificity_margin >= 0.15" not in hard
    assert "buried_anchor_contacts == 0" in hard


def test_od7_auto_resolved_merged_with_od5_screen_first_policy():
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-7"]
    assert od["status"] == "decided"
    assert od["resolution_mode"] == "auto_heuristic"
    assert od["merged_with"] == "OD-5"
    assert "SUPERSEDED" in od["resolution"]
    assert "screen-first" in od["resolution"].lower() or "SCREENING ORDER" in od["resolution"]
    assert "NOT as a selection filter" in od["resolution"] or "not as a selection filter" in od["resolution"].lower()
    assert "reopen_trigger" in od
    # Policy adopted, not wired — builder still has no pre-prediction liability screen.
    assert "NOTHING IS WIRED" in od["not_implemented"] or "not wire" in od["resolution"].lower()


def test_od10_remains_open_as_sole_campaign_approver_item():
    ods = {o["id"]: o for o in _fleet()["open_decisions"]}
    assert ods["OD-10"]["status"] == "open"
    assert ods["OD-10"]["roi"] == 5.00
    assert ods["OD-10"]["auto_resolve_eligible"] is False
    assert "spends money" in ods["OD-10"]["escalate_reason"].lower() or "spends" in ods["OD-10"]["escalate_reason"]
    # Among Campaign-approver ODs, only OD-10 is open after the ROI pass.
    open_approver = [
        o["id"]
        for o in _fleet()["open_decisions"]
        if o.get("status") == "open" and "Campaign approver" in o.get("owner", "")
    ]
    assert open_approver == ["OD-10"]
    # OD-4 stays deferred, not silently closed.
    assert ods["OD-4"]["status"] == "deferred"

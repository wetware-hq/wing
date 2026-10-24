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


def test_the_gate_itself_is_unchanged():
    # The dispersion is recorded as a fact; the decision stays open as OD-5.
    hard = _fleet()["gates"]["hard"]
    assert "specificity_margin >= 0.15" in hard
    assert "buried_anchor_contacts == 0" in hard
    assert "liability_filters.pass" in hard


def test_the_open_decision_is_recorded_and_still_open():
    ods = {o["id"]: o for o in _fleet()["open_decisions"]}
    assert "OD-5" in ods
    assert ods["OD-5"]["status"] == "open"
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
    assert od["status"] == "open"
    assert "evidence_seeded" in od


def test_seeding_is_still_not_implemented_because_od5_is_undecided():
    # Testing an option is not choosing it. The builder must send no sampler
    # options until OD-5 is decided by its owner.
    src = (CAMPAIGN / "l1b_request_builder.py").read_text()
    assert "model_options" not in src
    assert "seed" not in src
    od = {o["id"]: o for o in _fleet()["open_decisions"]}["OD-5"]
    assert "seeding is NOT implemented" in od["not_decided"]

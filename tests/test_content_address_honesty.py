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

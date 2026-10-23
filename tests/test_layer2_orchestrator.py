"""Unified L2 orchestrator: bundle schema, dual shell reporting, optional policy."""
import importlib.util
import json
import pathlib
import sys

import pytest

gemmi = pytest.importorskip("gemmi")

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_ONE = ROOT / "fleets" / "campaigns" / "NYESO1-A0201" / "run-one"
ARTIFACTS = RUN_ONE / "artifacts"
BUNDLE = ARTIFACTS / "layer2_bundle.json"
LEGACY = ARTIFACTS / "layer2_results.json"
FLAGS = RUN_ONE.parent / "targeting_flags.json"


def _load(name: str):
    path = RUN_ONE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_all():
    _load("contact_analysis")
    _load("specificity_scoring")
    return _load("layer2_core"), _load("tier0_targeting"), _load("layer2_orchestrator")


@pytest.fixture(scope="module")
def mods():
    return _load_all()


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="run-one artifacts not mirrored")
def test_bundle_has_dual_shell_and_ten_designs(mods):
    _, _, orch = mods
    payload = orch.run_bundle(ARTIFACTS, FLAGS, with_sasa=False, with_docking=True)
    assert payload["schema_version"].startswith("1.")
    assert len(payload["designs"]) == 10
    assert payload["parameters"]["item1_reporting_shells_angstrom"] == [10.0, 5.0]
    assert len(payload["tier0"]["designs"]) == 10
    assert len(payload["contact_site"]["designs"]) == 10
    for did, rec in payload["designs"].items():
        rep = rec["item1_shell_reporting"]
        assert "10.0" in rep and "5.0" in rep
        assert rec["tier0"]["item_3_buried_anchor_contact_count"] == 0
        assert rec["provenance"]["job_id"] == "prot_des_TY6KzyxULq8mACflXbhn"
        assert rec["item10_docking"]["complementarity_contact_fraction_delta"] is not None
        assert "verdict" in rec["contact_site"]


def test_buried_anchor_policy_flags_failures(mods):
    core, _, _ = mods
    assert core.evaluate_l2_policies({"item_3_buried_anchor_contact_count": 0}, ("buried-anchors-zero",))[
        "item_3_buried_anchors_zero"
    ] == "pass"
    assert core.evaluate_l2_policies({"item_3_buried_anchor_contact_count": 1}, ("buried-anchors-zero",))[
        "item_3_buried_anchors_zero"
    ] == "fail"


@pytest.mark.skipif(not LEGACY.is_file(), reason="legacy layer2_results missing")
def test_ipsae_matches_legacy_when_bindi_present(mods):
    _, _, orch = mods
    try:
        import bindi.ipsae  # noqa: F401
    except ImportError:
        pytest.skip("bindi not installed")
    payload = orch.run_bundle(ARTIFACTS, FLAGS, with_sasa=False, with_docking=False, with_contact_site=False)
    legacy = json.loads(LEGACY.read_text())
    for did, leg in legacy.items():
        new = payload["designs"][did]["ipsae"]
        if leg.get("score_error") or new.get("score_error"):
            continue
        assert new["min_ipsae_overall"] == leg["min_ipsae_overall"]
        assert new["iptm"] == leg["iptm"]

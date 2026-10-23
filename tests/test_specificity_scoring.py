"""Specificity margin + liability filters (unit + run-one integration)."""
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_ONE = ROOT / "fleets" / "campaigns" / "NYESO1-A0201" / "run-one"
ARTIFACTS = RUN_ONE / "artifacts"
DECOY_PANEL = (
    ROOT / "fleets" / "campaigns" / "NYESO1-A0201-specificity" / "decoy_panel.yaml"
)


def _load(name: str):
    path = RUN_ONE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def spec_mod():
    _load("contact_analysis")
    _load("layer2_core")
    return _load("specificity_scoring")


def test_motif_scan_finds_ng(spec_mod):
    hits = spec_mod.scan_motifs("ACNGDE")
    assert any(h["motif"] == "NG" for h in hits)


def test_liability_hard_fail_cys(spec_mod):
    lf = spec_mod.liability_filters("ACDEFGHC")
    assert lf["pass"] is False
    assert lf["unpaired_cys"]["hard_fail"] is True


def test_margin_computed_when_decoys_present(spec_mod):
    margin = spec_mod.compute_margin(0.50, {"d1": 0.20, "d2": 0.35})
    assert margin["specificity_margin"] == pytest.approx(0.15)
    assert margin["margin_status"] == "computed"
    assert margin["on_target_rank"] == 1


def test_margin_pending_without_decoys(spec_mod):
    margin = spec_mod.compute_margin(0.40, {"d1": None})
    assert margin["specificity_margin"] is None
    assert margin["margin_status"] == "pending_l1b"


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="run-one artifacts missing")
def test_specificity_bundle_on_run_one(spec_mod):
    tier0 = _load("tier0_targeting")
    orch = _load("layer2_orchestrator")
    flags = RUN_ONE.parent / "targeting_flags.json"
    payload = orch.run_bundle(
        ARTIFACTS,
        flags,
        with_sasa=False,
        with_docking=False,
        with_contact_site=False,
        decoy_panel_path=DECOY_PANEL,
        with_specificity=True,
        campaign_id="NYESO1-A0201-specificity",
    )
    assert payload["primary_endpoint"] == "specificity_margin"
    assert len(payload["designs"]) == 10
    panel = payload["panel"]
    assert panel["handoff"]["top_n"] == 3
    assert len(panel["handoff"]["designs"]) <= 3
    try:
        import bindi.ipsae  # noqa: F401
        has_bindi = True
    except ImportError:
        has_bindi = False
    for did, rec in payload["designs"].items():
        assert rec.get("binder_sequence")
        status = rec["specificity"]["margin_status"]
        if has_bindi:
            assert status == "pending_l1b"
        else:
            assert status in ("pending_l1b", "missing_on_target_score")
        assert "pass" in rec["liability_filters"]
        if not rec["liability_filters"]["pass"]:
            assert rec["gates"]["hard_pass"] is False
    assert panel["pins"]["worker_wheel_sha256"]


def test_decoy_panel_has_ten_mutants(spec_mod):
    panel = spec_mod.load_decoy_panel(DECOY_PANEL)
    assert panel["cognate"]["sequence"] == "SLLMWITQC"
    assert len(panel["mutants"]) == 10
    classes = [m["class"] for m in panel["mutants"]]
    assert classes.count("single") == 7
    assert classes.count("double") == 2
    assert classes.count("triple") == 1
    assert panel.get("panel_ready_for_l1b") is True

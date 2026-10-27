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
            assert status in ("pending_l1b", "computed")
        else:
            assert status in ("pending_l1b", "missing_on_target_score", "computed")
        assert "pass" in rec["liability_filters"]
        if not rec["liability_filters"]["pass"]:
            assert rec["gates"]["hard_pass"] is False
    assert panel["pins"]["worker_wheel_sha256"]


def test_decoy_panel_has_ten_mutants(spec_mod):
    panel = spec_mod.load_decoy_panel(DECOY_PANEL)
    assert panel["cognate"]["sequence"] == "SLLMWITQC"
    # OD-3 ten-mutant panel is invariant; Arm B adds W5Y as an extension.
    od3 = [m for m in panel["mutants"] if m.get("arm") != "ARM_B_DISCRIMINATING_MUTANT"]
    arm_b = [m for m in panel["mutants"] if m.get("id") == "decoy_p5_w_to_y"]
    assert len(od3) == 10
    assert panel["composition"]["total"] == 10
    classes = [m["class"] for m in od3]
    assert classes.count("single") == 7
    assert classes.count("double") == 2
    assert classes.count("triple") == 1
    assert panel.get("panel_ready_for_l1b") is True
    # Arm B W5Y extension (PHYSICIAN_SIGNOFF_2026-10-27.md)
    assert len(arm_b) == 1
    assert arm_b[0]["sequence"] == "SLLMYITQC"
    cognate = panel["cognate"]["sequence"]
    w5y = arm_b[0]["sequence"]
    diffs = [(i + 1, a, b) for i, (a, b) in enumerate(zip(cognate, w5y)) if a != b]
    assert diffs == [(5, "W", "Y")]
    assert panel.get("arm_b_extension", {}).get("mutant_id") == "decoy_p5_w_to_y"

# ---------------------------------------------------------------------------
# developability_score honesty
#
# developability_score was computed from sequence motif hits alone while
# `pass` also counted unpaired cysteine, exposed oxidation, N-terminal
# glutamine and poly-Q. A design whose only liability was one of those four
# reported a perfect 1.0 from the same dict that declared it a hard fail.
# The real case is pres_G3ZfGGLFJXddOc0vhQwO: zero motif hits (score 1.0)
# but 3 Met and 2 Trp, so exposed_oxidation.hard_fail is True. The score is
# also the panel's secondary rank key, so the lie was not confined to
# reporting. This is not a second gate: `pass` remains the only verdict.
# ---------------------------------------------------------------------------

# Verbatim from artifacts/layer2_bundle.json.
_G3ZF_SEQ = (
    "MDEGARLYELTAAHPELQEEALRLLTEWEATHRLSMEQQLELTARMAEWLAETSDVEEFRERLREALEELLAR"
)

# Sequences of the two designs that genuinely pass, which must be unaffected.
_CLEAN_SEQS = {
    "pres_Bw8vknhmXJUg72L6CGAw": (
        "SLEEAVEFAGRALDKIFAGEALSEEERRRLEEALRLARATVERLGGALDEEGRLAAEAENLARTTLAAEALRA"
    ),
    "pres_PfYJkQdsLag9x1R5Pt6L": (
        "VEVLEENDETVKLYAKKGETLGEAEAKAKEIAASKGYDDAVITGVLEGDVPQDARLDDVLAVDAVLEFRFVSD"
    ),
}


def test_g3zf_really_is_the_case_described(spec_mod):
    """Guard the premise, so this test cannot silently stop testing anything."""
    liab = spec_mod.liability_filters(_G3ZF_SEQ)
    assert liab["motif_hits"] == []
    assert liab["exposed_oxidation"]["residue_counts"] == {"M": 3, "W": 2}
    assert liab["exposed_oxidation"]["hard_fail"] is True
    assert liab["pass"] is False


def test_g3zf_does_not_report_a_perfect_developability_score(spec_mod):
    """The headline defect: dead by the gate, perfect by the score."""
    liab = spec_mod.liability_filters(_G3ZF_SEQ)
    assert liab["pass"] is False
    assert liab["developability_score"] != 1.0


def test_no_hard_failing_sequence_can_present_as_clean(spec_mod):
    """The general invariant, over every liability the gate recognises."""
    cases = [
        _G3ZF_SEQ,
        "QLEEAVEFAGRALDKIFAGEALSEEERRRLEEALRLARATVERLGGALDEEGRLAAEAENLARTTLAAEALRA",
        "SLEEAVEFAGRALDKIFAGEALSEEERRRLEEALRLARATVERLGGALDEEGRLAAEAENLARTTLAAEALRC",
        "SLEEAVEFAGRALDKIFAGEALSEEERRRLEEALRLARATVERLGGALDEEGRLAAEAENLARTTLQQQQQQA",
    ]
    for seq in cases:
        liab = spec_mod.liability_filters(seq)
        assert liab["pass"] is False, f"expected a hard fail for {seq[:12]}..."
        assert liab["developability_score"] == 0.0, (
            f"hard-failing sequence {seq[:12]}... reported "
            f"developability_score={liab['developability_score']}"
        )


def test_the_hard_fail_verdict_travels_with_the_score(spec_mod):
    """The score and the verdict must not be separable by a consumer."""
    liab = spec_mod.liability_filters(_G3ZF_SEQ)
    assert liab["developability_score_hard_failed"] is True
    # The motif-only quantity is preserved, not destroyed, under its own name.
    assert liab["developability_motif_subscore"] == 1.0


def test_genuinely_clean_designs_are_unchanged(spec_mod):
    for design_id, seq in _CLEAN_SEQS.items():
        liab = spec_mod.liability_filters(seq)
        assert liab["pass"] is True, design_id
        assert liab["developability_score"] == 1.0, design_id
        assert liab["developability_score_hard_failed"] is False, design_id

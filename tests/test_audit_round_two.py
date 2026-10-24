"""Regressions for the second audit pass.

Every one of these is the same failure mode: the pipeline produced a result
that looked valid instead of failing. Each test was confirmed failing before
its fix.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_ONE = ROOT / "fleets/campaigns/NYESO1-A0201/run-one"
CAMPAIGN = ROOT / "fleets/campaigns/NYESO1-A0201-specificity"
for _p in (RUN_ONE, CAMPAIGN):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import specificity_scoring as ss  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sm = _load("specificity_margin", CAMPAIGN / "specificity_margin.py")
so = _load("specificity_orchestrator", CAMPAIGN / "specificity_orchestrator.py")


# --------------------------------------------------------------- tied ranks


def test_tied_values_share_the_mean_rank_instead_of_list_order():
    # The cognate is inserted first by construction, so ordinal ranking handed
    # it rank 1 on a descriptor where every peptide scored identically.
    assert sm.average_rank([5.0, 5.0, 5.0, 1.0], True) == {0: 2.0, 1: 2.0, 2: 2.0, 3: 4.0}


def test_a_two_way_tie_splits_the_positions_it_spans():
    assert sm.average_rank([9.0, 5.0, 5.0, 1.0], True) == {0: 1.0, 1: 2.5, 2: 2.5, 3: 4.0}


def test_a_panel_with_no_discriminating_signal_yields_no_margin():
    rows = [
        {"peptide_id": p, "iptm": 0.5, "plddt": 80.0, "ipsae": 0.3, "min_ipsae": 0.3}
        for p in ("cognate", "decoy_a", "decoy_b")
    ]
    out = sm.compute_specificity_margin(
        rows,
        cognate_peptide_id="cognate",
        decoy_peptide_ids=["decoy_a", "decoy_b"],
        stack=("iptm", "plddt", "ipsae", "min_ipsae"),
    )
    assert out["rank_margin"] == 0
    assert out["pass_in_silico_draft"] is False


# -------------------------------------------------- Path B field is renamed


def test_path_b_does_not_publish_its_ordinal_under_the_path_a_gate_name():
    rows = [
        {"peptide_id": "cognate", "iptm": 0.9, "plddt": 90.0, "ipsae": 0.5, "min_ipsae": 0.5},
        {"peptide_id": "decoy_a", "iptm": 0.1, "plddt": 50.0, "ipsae": 0.1, "min_ipsae": 0.1},
    ]
    out = sm.compute_specificity_margin(
        rows,
        cognate_peptide_id="cognate",
        decoy_peptide_ids=["decoy_a"],
        stack=("iptm", "plddt", "ipsae", "min_ipsae"),
    )
    assert "specificity_margin" not in out
    assert out["margin_scale"] == "ordinal_rank_difference"


# ------------------------------------------------------ decoy panel sanity


def _doc(**kw):
    base = {"cognate": {"peptide_id": "cognate", "sequence": "SLLMWITQC"}, "mutants": []}
    base.update(kw)
    return base


def test_an_empty_decoy_panel_is_rejected_by_name():
    with pytest.raises(SystemExit, match="decoy panel is empty"):
        so.build_ranked_panel(
            [], _doc(), Path("/tmp"), Path("/tmp/flags.json"), score=False, stack=()
        )


def test_a_duplicated_decoy_is_rejected():
    doc = _doc(mutants=[{"id": "d1", "sequence": "A"}, {"id": "d1", "sequence": "A"}])
    with pytest.raises(SystemExit, match="duplicate peptide_ids"):
        so.build_ranked_panel(
            [], doc, Path("/tmp"), Path("/tmp/flags.json"), score=False, stack=()
        )


def test_the_cognate_cannot_also_be_a_decoy():
    doc = _doc(mutants=[{"id": "cognate", "sequence": "SLLMWITQC"}])
    with pytest.raises(SystemExit, match="cannot be its own decoy"):
        so.build_ranked_panel(
            [], doc, Path("/tmp"), Path("/tmp/flags.json"), score=False, stack=()
        )


# ----------------------------------------- cognate row selected by identity


def test_the_handoff_reads_the_cognate_row_by_id_not_by_position():
    design = {
        "margin": {
            "on_target_peptide_id": "cognate",
            "peptide_rows": [
                {"peptide_id": "decoy_a", "contact_site": "WRONG"},
                {"peptide_id": "cognate", "contact_site": "RIGHT"},
            ],
        }
    }
    assert so._cognate_row(design)["contact_site"] == "RIGHT"


def test_a_design_with_no_cognate_row_yields_none_rather_than_a_decoy():
    design = {"margin": {"on_target_peptide_id": "cognate", "peptide_rows": [
        {"peptide_id": "decoy_a", "contact_site": "WRONG"}
    ]}}
    assert so._cognate_row(design) is None


# ------------------------------------------- unmeasured is not a pass value


def test_an_honest_iptm_of_zero_is_not_converted_to_a_sentinel():
    rows = [
        {"design_id": "a", "specificity": {"specificity_margin": 0.2},
         "liability_filters": {"developability_score": 0.5}, "iptm": 0.0},
        {"design_id": "b", "specificity": {"specificity_margin": 0.2},
         "liability_filters": {"developability_score": 0.5}, "iptm": None},
    ]
    assert [r["design_id"] for r in ss.rank_panel_rows(rows)] == ["a", "b"]


# ------------------------------------------------------ rejection store


ALL_PINNED = {"all_pinned": True, "unpinned_gates": [], "findings": [], "checked": []}


def _panel(**kw):
    bundle = {
        "designs": {
            "d_fail": {
                "binder_sequence": "AAAA",
                "liability_filters": {"pass": False, "developability_score": 0.3},
                "specificity": {"specificity_margin": 0.02, "margin_status": "computed"},
                "tier0": {"item_3_buried_anchor_contact_count": 0},
                "gates": {"hard_pass": False,
                          "fail_reasons": ["liability_filters:fail", "specificity_margin:0.02<0.15"]},
            }
        }
    }
    return ss.build_panel_payload(bundle, config_pins_report=ALL_PINNED, **kw)


def test_a_rejected_design_gets_a_structured_record():
    recs = ss.rejection_records(_panel())
    assert len(recs) == 1
    assert recs[0]["design_id"] == "d_fail"
    assert set(recs[0]["reason_codes"]) == {"liability", "specificity_margin"}


def test_a_fail_reason_outside_the_taxonomy_is_named_rather_than_dropped():
    out = ss.classify_fail_reasons(["buried_anchor_contacts:unmeasured"])
    assert out["reason_codes"] == []
    assert out["unclassified_fail_reasons"] == ["buried_anchor_contacts:unmeasured"]


def test_every_mapped_code_is_one_fleet_toml_declares():
    for _prefix, code in ss._REASON_CODES:
        assert code in ss.REASON_TAXONOMY


def test_the_rejection_store_is_actually_written(tmp_path):
    path = tmp_path / "rejections.jsonl"
    n = ss.write_rejections(_panel(), path)
    assert n == 1
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert lines[0]["design_id"] == "d_fail"


# ------------------------------------------- a failed design blocks handoff


def test_a_design_that_raised_blocks_the_handoff_and_appears_in_the_panel():
    bundle = {
        "designs": {
            "d_pass": {
                "binder_sequence": "AAAA",
                "liability_filters": {"pass": True, "developability_score": 0.9},
                "specificity": {"specificity_margin": 0.4, "margin_status": "computed"},
                "tier0": {"item_3_buried_anchor_contact_count": 0},
                "gates": {"hard_pass": True, "fail_reasons": []},
            }
        },
        "errors": {"d_broken": "ChainLayoutError: chain D absent"},
    }
    payload = ss.build_panel_payload(
        bundle, config_pins_report=ALL_PINNED, design_errors=bundle["errors"]
    )
    assert payload["handoff"]["designs"] == []
    assert payload["handoff"]["blocked_by_design_errors"] == ["d_broken"]
    assert payload["design_errors"]["d_broken"].startswith("ChainLayoutError")
    assert "d_broken" in payload["handoff"]["note"]


# ------------------------------------------------- the pin check itself


cp = _load("config_pins", CAMPAIGN / "config_pins.py")


def _campaign(tmp_path: Path, fleet: str, **files: str) -> Path:
    (tmp_path / "FLEET.toml").write_text(fleet)
    for name, body in files.items():
        (tmp_path / name.replace("__", ".")).write_text(body)
    return tmp_path


def test_a_missing_ortholog_panel_is_unpinned_not_pinned(tmp_path):
    # Deleting the file must not be a way to make the gate report pinned.
    d = _campaign(tmp_path, '[species_cross_reactivity]\npanel = "ortholog_panel.yaml"\n')
    report = cp.collect_unpinned(d / "FLEET.toml", d)
    assert report["all_pinned"] is False
    assert "species_cross_reactivity" in report["unpinned_gates"]


def test_a_deferred_panel_is_unpinned_even_with_every_sequence_filled(tmp_path):
    d = _campaign(
        tmp_path,
        '[species_cross_reactivity]\npanel = "ortholog_panel.yaml"\n',
        ortholog_panel__yaml=(
            "status: deferred\northologs:\n"
            "  - species: murine\n    sequence: SLLMWITQA\n"
        ),
    )
    report = cp.collect_unpinned(d / "FLEET.toml", d)
    assert report["all_pinned"] is False


def test_a_fully_pinned_panel_reports_pinned(tmp_path):
    d = _campaign(
        tmp_path,
        '[species_cross_reactivity]\npanel = "ortholog_panel.yaml"\n',
        ortholog_panel__yaml=(
            "status: pinned\northologs:\n"
            "  - species: murine\n    sequence: SLLMWITQA\n"
        ),
    )
    report = cp.collect_unpinned(d / "FLEET.toml", d)
    assert report["all_pinned"] is True


def test_calibration_without_scored_each_run_is_unevaluable_not_inactive(tmp_path):
    d = _campaign(tmp_path, '[calibration]\nanchors_file = "calibration_anchors.yaml"\n')
    report = cp.collect_unpinned(d / "FLEET.toml", d)
    assert "calibration" in report["unpinned_gates"]


def test_a_campaign_with_no_declared_gates_is_pinned(tmp_path):
    # The checks must not invent findings where FLEET.toml declares nothing.
    d = _campaign(tmp_path, "[gates]\nhard = []\n")
    assert cp.collect_unpinned(d / "FLEET.toml", d)["all_pinned"] is True


# --------------------------------------------- absent is never a free pass


def test_path_b_refuses_to_build_a_handoff_without_a_pin_report():
    with pytest.raises(ValueError, match="config_pins_report is required"):
        so.transport_payload(
            {"designs": [], "campaign_id": "x", "config_manifest_hash": "y"}
        )


def test_no_hardcoded_source_job_id_is_substituted():
    doc = _doc(mutants=[{"id": "d1", "sequence": "A"}])
    panel = so.build_ranked_panel(
        [{"design_id": "pres_x", "binder_sequence": "AAAA"}],
        doc,
        Path("/tmp/nonexistent-artifacts"),
        Path("/tmp/flags.json"),
        score=False,
        stack=(),
    )
    assert panel["designs"][0]["source_job_id"] is None


def test_an_unmeasured_developability_score_sorts_last_rather_than_reading_as_zero():
    rows = [
        {"design_id": "measured_low", "specificity": {"specificity_margin": 0.2},
         "liability_filters": {"developability_score": 0.01}, "iptm": 0.5},
        {"design_id": "unmeasured", "specificity": {"specificity_margin": 0.2},
         "liability_filters": {"developability_score": None}, "iptm": 0.5},
    ]
    assert [r["design_id"] for r in ss.rank_panel_rows(rows)] == ["measured_low", "unmeasured"]


def test_a_design_with_no_liability_block_does_not_crash_the_panel_build():
    rows = [{"design_id": "a", "specificity": {"specificity_margin": 0.2},
             "liability_filters": None, "iptm": 0.5}]
    assert ss.rank_panel_rows(rows)[0]["design_id"] == "a"

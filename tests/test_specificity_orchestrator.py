"""Path B artifact-reader tests: collect_peptide_artifact_dirs must see both layouts.

Regression guard for the bug where a cognate ``*_predicted.cif`` sitting directly in
``artifacts/<design_id>/`` made the reader return early, hiding every L1B decoy refold
under ``artifacts/decoy_refolds/<design_id>/<decoy_id>/`` (100 result dirs on the real
run) and leaving ``ranked_panel.json`` reporting "missing decoy rows".
"""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "fleets" / "campaigns" / "NYESO1-A0201-specificity"

DECOY_IDS = [
    "decoy_p4_m_to_v",
    "decoy_p4_m_to_a",
    "decoy_p5_w_to_a",
    "decoy_p5_w_to_f",
    "decoy_p6_i_to_a",
    "decoy_p7_t_to_a",
    "decoy_p8_q_to_a",
    "decoy_p4v_p5a",
    "decoy_p6a_p7a",
    "decoy_p4_p5_p6_triple",
]


def _load_so():
    sys.path.insert(0, str(SPEC))
    try:
        path = SPEC / "specificity_orchestrator.py"
        spec = importlib.util.spec_from_file_location("specificity_orchestrator", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["specificity_orchestrator"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(SPEC))


def _write_prediction(d: pathlib.Path, stem: str) -> pathlib.Path:
    """Minimal stand-in for one Boltz result dir (contents are never parsed here)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}_predicted.cif").write_text("data_stub\n")
    (d / "metrics.json").write_text("{}")
    (d / "pae.npz").write_bytes(b"")
    return d


def _make_run_one_shape(root: pathlib.Path, design_id: str) -> None:
    """Cognate .cif directly in artifacts/<design_id>/, decoys under decoy_refolds/."""
    _write_prediction(root / design_id, design_id)
    for decoy_id in DECOY_IDS:
        _write_prediction(root / "decoy_refolds" / design_id / decoy_id, decoy_id)


def test_reader_returns_cognate_and_all_decoy_refolds(tmp_path):
    so = _load_so()
    design_id = "pres_rIVnI2qWY81pul3zHRrN"
    _make_run_one_shape(tmp_path, design_id)

    out = so.collect_peptide_artifact_dirs(design_id, tmp_path)

    assert set(out) == {"cognate_SLLMWITQC", *DECOY_IDS}
    assert len(out) == 1 + len(DECOY_IDS)
    assert out["cognate_SLLMWITQC"] == tmp_path / design_id
    for decoy_id in DECOY_IDS:
        assert out[decoy_id] == tmp_path / "decoy_refolds" / design_id / decoy_id


def test_reader_does_not_cross_designs(tmp_path):
    so = _load_so()
    _make_run_one_shape(tmp_path, "pres_AAA")
    _make_run_one_shape(tmp_path, "pres_BBB")

    out = so.collect_peptide_artifact_dirs("pres_AAA", tmp_path)

    assert len(out) == 1 + len(DECOY_IDS)
    assert all("pres_BBB" not in str(p) for p in out.values())


def test_reader_still_handles_legacy_per_peptide_subtree(tmp_path):
    so = _load_so()
    design_id = "pres_legacy"
    _write_prediction(tmp_path / design_id / "cognate_SLLMWITQC", "cognate_SLLMWITQC")
    _write_prediction(tmp_path / design_id / "decoy_p4_m_to_v", "decoy_p4_m_to_v")

    out = so.collect_peptide_artifact_dirs(design_id, tmp_path)

    assert set(out) == {"cognate_SLLMWITQC", "decoy_p4_m_to_v"}


def test_reader_cognate_only_when_no_decoys(tmp_path):
    so = _load_so()
    design_id = "pres_solo"
    _write_prediction(tmp_path / design_id, design_id)

    out = so.collect_peptide_artifact_dirs(design_id, tmp_path)

    assert set(out) == {"cognate_SLLMWITQC"}


def test_reader_empty_for_unknown_design(tmp_path):
    so = _load_so()
    assert so.collect_peptide_artifact_dirs("pres_missing", tmp_path) == {}


def test_reader_sees_real_run_one_tree():
    """The committed run-one tree: 1 cognate + 10 decoy dirs per survivor, 110 total."""
    so = _load_so()
    artifacts = SPEC.parent / "NYESO1-A0201" / "run-one" / "artifacts"
    if not (artifacts / "decoy_refolds").is_dir():
        import pytest

        pytest.skip("run-one artifacts not present in this checkout")
    survivors = sorted(p.name for p in artifacts.iterdir() if p.name.startswith("pres_"))
    assert len(survivors) == 10
    total = 0
    for sid in survivors:
        dirs = so.collect_peptide_artifact_dirs(sid, artifacts)
        assert "cognate_SLLMWITQC" in dirs
        assert len(dirs) == 11, f"{sid}: {sorted(dirs)}"
        total += len(dirs)
    assert total == 110

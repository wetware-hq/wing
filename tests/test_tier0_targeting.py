"""The Tier 0 targeting metrics must compute UPGRADES.md's definitions, and must not gate.

Two things are pinned here. First the arithmetic: the epitope shell is DERIVED from the
hotspots rather than declared, and each fraction is a ratio of contacted residues exactly
as BindCraft2 defines it. Second, and more important, the discipline: UPGRADES.md marks
items 1-3 as proposals needing the user's decision, so no threshold may appear anywhere in
this layer and FLEET.toml's gating descriptors must stay iptm and plddt only.
"""
import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

gemmi = pytest.importorskip("gemmi", reason="targeting metrics need gemmi for CIF coordinates")

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAMPAIGN = ROOT / "fleets" / "campaigns" / "NYESO1-A0201"
RUN_ONE = CAMPAIGN / "run-one"
FLAGS = CAMPAIGN / "targeting_flags.json"
RESULTS = RUN_ONE / "tier0_targeting_results.json"


def _load(name):
    path = RUN_ONE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load("contact_analysis")
t0 = _load("tier0_targeting")


def _chain(seq_ids, coords):
    import contact_analysis as ca

    return ca.ChainAtoms(
        chain_id="X",
        coords=np.asarray(coords, dtype=float),
        atom_seq_ids=np.asarray(seq_ids, dtype=int),
        residue_names={int(s): "ALA" for s in seq_ids},
    )


def test_flags_file_is_loadable_and_declares_the_campaign_intent():
    flags = t0.load_flags(FLAGS)
    assert flags["epitope_shell_cutoff_angstrom"] == 10.0
    assert flags["contact_cutoff_angstrom"] == 4.0
    assert flags["hotspots"]["C"] == [4, 5, 6, 7, 8]
    assert flags["buried_anchors"]["C"] == [2, 9]
    assert flags["invariant_surface_chains"] == ["A", "B"]
    assert flags["discriminating_surface_chains"] == ["C"]


def test_coldspot_ambiguity_is_recorded_rather_than_quietly_resolved():
    """The 'rim' is undefined in the source. Pretending otherwise is the failure mode."""
    flags = t0.load_flags(FLAGS)
    assert "_coldspot_ambiguity" in flags["coldspots"]
    assert "DECISION PENDING" in flags["coldspots"]["_definition"]


def test_contacted_residues_is_a_residue_set_not_an_atom_count():
    """Two atoms of one residue in range must count once: these are residue fractions."""
    binder = _chain([1, 1], [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]])
    target = _chain([7, 7, 8], [[1.0, 0.0, 0.0], [1.5, 0.0, 0.0], [50.0, 0.0, 0.0]])
    assert t0.contacted_residues(binder, target, 4.0) == {7}


def test_contact_cutoff_is_exclusive_above_and_inclusive_at_the_boundary():
    binder = _chain([1], [[0.0, 0.0, 0.0]])
    target = _chain([7, 8], [[4.0, 0.0, 0.0], [4.001, 0.0, 0.0]])
    assert t0.contacted_residues(binder, target, 4.0) == {7}


def test_epitope_shell_is_derived_from_hotspots_by_minimum_atom_distance():
    """G7's whole point: one statement of intent generates both criteria."""
    import contact_analysis as ca

    chains = {
        ca.PEPTIDE_CHAIN: _chain([4, 5], [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        ca.HEAVY_CHAIN: _chain([10, 11], [[9.0, 0.0, 0.0], [40.0, 0.0, 0.0]]),
    }
    flags = {"epitope_shell_cutoff_angstrom": 10.0, "hotspots": {ca.PEPTIDE_CHAIN: [4, 5]}}
    shell = t0.epitope_shell(chains, flags, (ca.HEAVY_CHAIN,))
    assert shell[ca.HEAVY_CHAIN] == {10}, "residue 11 is 39 A from the nearest hotspot atom"


def test_a_wider_shell_can_only_grow_the_shell():
    """Monotonicity. If this ever fails the 'shell swallows the surface' caveat is wrong."""
    import contact_analysis as ca

    chains = {
        ca.PEPTIDE_CHAIN: _chain([4], [[0.0, 0.0, 0.0]]),
        ca.HEAVY_CHAIN: _chain([10, 11, 12], [[5.0, 0, 0], [15.0, 0, 0], [25.0, 0, 0]]),
    }
    base = {"hotspots": {ca.PEPTIDE_CHAIN: [4]}}
    small = t0.epitope_shell(chains, {**base, "epitope_shell_cutoff_angstrom": 10.0}, (ca.HEAVY_CHAIN,))
    big = t0.epitope_shell(chains, {**base, "epitope_shell_cutoff_angstrom": 20.0}, (ca.HEAVY_CHAIN,))
    assert small[ca.HEAVY_CHAIN] < big[ca.HEAVY_CHAIN]


@pytest.mark.skipif(not RESULTS.exists(), reason="tier0 results not generated")
class TestRecordedResults:
    @staticmethod
    def _payload():
        return json.loads(RESULTS.read_text())

    def test_every_design_scored_with_no_errors(self):
        p = self._payload()
        assert p["errors"] == {}
        assert len(p["designs"]) == 10

    def test_results_are_labelled_non_gating(self):
        p = self._payload()
        assert p["status"] == "RECORDED-NON-GATING"
        assert "no calibrated threshold" in p["gating_warning"]

    def test_fractions_are_in_range_and_anchors_are_untouched(self):
        for name, rec in self._payload()["designs"].items():
            for key in (
                "item_1_off_epitope_contact_fraction",
                "item_2_coldspot_contact_fraction",
                "hotspot_contact_fraction",
            ):
                v = rec[key]
                assert v is None or 0.0 <= v <= 1.0, f"{name}.{key} = {v}"
            assert rec["item_3_buried_anchor_contact_count"] == 0, (
                f"{name} contacts a buried anchor position - a geometric red flag about "
                "the pose, per UPGRADES.md item 3"
            )

    def test_parameters_are_recorded_with_the_numbers(self):
        """A number whose shell cutoff is not stored beside it is not reproducible."""
        params = self._payload()["parameters"]
        assert params["epitope_shell_cutoff_angstrom"] == 10.0
        assert params["contact_cutoff_angstrom"] == 4.0
        assert params["hotspots"]["C"] == [4, 5, 6, 7, 8]


def test_no_threshold_leaks_into_the_tier0_layer():
    """Items 1-3 are GATING-PROPOSED. Until the user decides, nothing here may compare.

    Checked against the module's EXECUTABLE code only. Docstrings are allowed - and are
    required - to name the teacher's settings and explain why they are not inherited;
    what must not exist is a line that acts on one.
    """
    import ast

    tree = ast.parse((RUN_ONE / "tier0_targeting.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant(value="")
    code = ast.unparse(tree)
    for banned in ("max_off_epitope", "min_hotspot_contact", "PASS", "FAIL"):
        assert banned not in code, f"{banned!r} suggests a gate crept into executable code"

    metrics = {
        "off_epitope",
        "coldspot_contact",
        "hotspot_contact",
        "invariant_surface_fraction",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        rendered = ast.unparse(node)
        if any(m in rendered for m in metrics) and any(
            isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in node.ops
        ):
            raise AssertionError(f"a metric is being thresholded: {rendered}")


def test_fleet_toml_gating_descriptors_are_untouched_by_this_work():
    """UPGRADES.md header: no gate in FLEET.toml is changed by that document."""
    toml = (CAMPAIGN / "FLEET.toml").read_text()
    for name in ("off_epitope", "coldspot_contact_fraction", "invariant_surface_fraction"):
        assert name not in toml, (
            f"{name} appears in FLEET.toml; a recorded-non-gating metric was promoted to a "
            "gate without the user's decision"
        )

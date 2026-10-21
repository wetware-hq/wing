"""The run-one contact analysis must classify by WHERE the binder sits, not by raw counts.

A 9-residue peptide is out-counted by a 275-residue heavy chain by construction, which is
the bias that made the ipSAE A|D > C|D ordering uninterpretable. These tests pin the
interpretive rule that replaces it: zero P4-P8 contact is framework-directed no matter how
good iptm looks, and broad P4-P8 engagement with only groove-proximal framework footing is
peptide-directed even when chain A out-counts the peptide.
"""
import importlib.util
import pathlib
import sys

import pytest

gemmi = pytest.importorskip("gemmi", reason="contact analysis needs gemmi for CIF coordinates")

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "fleets" / "campaigns" / "NYESO1-A0201" / "run-one" / "contact_analysis.py"
ARTIFACTS = MODULE_PATH.parent / "artifacts"


def _load():
    spec = importlib.util.spec_from_file_location("contact_analysis", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations via sys.modules[__module__].
    sys.modules["contact_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


ca = _load()


def _peptide(per_pos):
    """Build a peptide breakdown the way contact_analysis derives it from contacts()."""
    return ca.peptide_breakdown({"per_residue_b": {p: n for p, n in per_pos.items() if n}})


def _chain_a(by_residue):
    return ca.heavy_chain_breakdown({"per_residue_b": by_residue})


def test_chain_a_regions_tile_the_whole_heavy_chain_without_gaps_or_overlap():
    """A contacted residue must land in exactly one region, or region fractions lie."""
    covered = []
    for _, lo, hi in ca.CHAIN_A_REGIONS:
        covered.extend(range(lo, hi + 1))
    assert sorted(covered) == list(range(1, 276))
    assert len(covered) == len(set(covered)), "regions overlap"
    assert all(ca.region_of(i) != "out_of_range" for i in range(1, 276))


def test_alpha3_and_b2m_are_treated_as_peptide_remote():
    assert ca.region_of(200) == "alpha3_Ig"
    assert "alpha3_Ig" in ca.PEPTIDE_REMOTE_REGIONS
    assert "alpha3_Ig" not in ca.GROOVE_PROXIMAL_REGIONS
    assert ca.region_of(70) == "alpha1_helix"
    assert ca.region_of(150) == "alpha2_helix"
    assert {"alpha1_helix", "alpha2_helix"} <= ca.GROOVE_PROXIMAL_REGIONS


def test_no_peptide_contact_is_framework_directed():
    verdict, reason, _ = ca.classify(
        _peptide({p: 0 for p in range(1, 10)}),
        _chain_a({70: 80, 150: 60}),
        b2m_atom_contacts=0,
    )
    assert verdict == "framework-directed"
    assert "does not touch" in reason


def test_anchor_only_contact_is_framework_directed_despite_touching_the_peptide():
    """P2/P9 are buried in the groove; touching them is groove-rim proximity, not readout."""
    verdict, _, _ = ca.classify(
        _peptide({2: 9, 9: 7}), _chain_a({70: 80}), b2m_atom_contacts=0
    )
    assert verdict == "framework-directed"


def test_broad_p4_p8_engagement_outvotes_a_larger_raw_chain_a_count():
    """THE point of the file: 60 peptide contacts across P4-P8 beat 300 groove-proximal
    chain A contacts, because counts are not size-normalised."""
    verdict, _, crit = ca.classify(
        _peptide({4: 10, 5: 20, 6: 10, 7: 10, 8: 10}),
        _chain_a({70: 150, 150: 150}),
        b2m_atom_contacts=0,
    )
    assert verdict == "peptide-directed"
    assert crit["tcr_facing_positions_hit"] == 5
    assert crit["groove_proximal_fraction_of_chainA"] == 1.0


def test_alpha3_or_b2m_contact_downgrades_even_with_broad_peptide_engagement():
    broad = _peptide({4: 10, 5: 20, 6: 10, 7: 10, 8: 10})
    v_a3, _, _ = ca.classify(broad, _chain_a({70: 100, 200: 12}), b2m_atom_contacts=0)
    assert v_a3.startswith("mixed")
    v_b2m, _, _ = ca.classify(broad, _chain_a({70: 100}), b2m_atom_contacts=5)
    assert v_b2m.startswith("mixed")


def test_sparse_peptide_engagement_is_mixed_not_peptide_directed():
    verdict, _, _ = ca.classify(
        _peptide({5: 3, 6: 2}), _chain_a({70: 50}), b2m_atom_contacts=0
    )
    assert verdict == "mixed (peptide-marginal)"


def test_peptide_breakdown_separates_tcr_facing_from_anchors():
    out = _peptide({2: 4, 5: 11, 8: 3, 9: 2})
    assert out["per_position_atom_contacts"][5] == 11
    assert out["tcr_facing_P4_P8_atom_contacts"] == 14
    assert out["tcr_facing_P4_P8_positions_hit"] == [5, 8]
    assert out["anchor_P2_P9_atom_contacts"] == 6
    assert out["positions_contacted"] == [2, 5, 8, 9]


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="run-one artifacts not mirrored here")
def test_mirrored_artifacts_have_the_chain_layout_this_campaign_assumes():
    """BINDER_CHAIN='D' came from a comment, not an artifact. Prove it against every CIF,
    and fail loudly rather than score the wrong interface."""
    cifs = sorted(ARTIFACTS.glob("pres_*/pres_*_predicted.cif"))
    assert len(cifs) == 10, f"expected 10 mirrored designs, found {len(cifs)}"
    for cif in cifs:
        chains = ca.load_chains(cif)
        ca.assert_layout(chains, cif)  # raises ChainLayoutError on any mismatch
        assert chains[ca.BINDER_CHAIN].n_residues == 73


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="run-one artifacts not mirrored here")
def test_wrong_chain_lettering_is_rejected_rather_than_silently_scored():
    cif = sorted(ARTIFACTS.glob("pres_*/pres_*_predicted.cif"))[0]
    chains = ca.load_chains(cif)
    mangled = {k: v for k, v in chains.items() if k != ca.PEPTIDE_CHAIN}
    with pytest.raises(ca.ChainLayoutError):
        ca.assert_layout(mangled, cif)


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason="run-one artifacts not mirrored here")
def test_contacts_are_monotonic_in_cutoff():
    """A 5.0 A shell must contain the 4.0 A shell, or the geometry code is wrong."""
    cif = sorted(ARTIFACTS.glob("pres_*/pres_*_predicted.cif"))[0]
    chains = ca.load_chains(cif)
    binder = chains[ca.BINDER_CHAIN]
    for partner in (ca.HEAVY_CHAIN, ca.PEPTIDE_CHAIN):
        near = ca.contacts(binder, chains[partner], 4.0)
        far = ca.contacts(binder, chains[partner], 5.0)
        assert far["atom_pairs"] >= near["atom_pairs"]
        assert far["residue_pairs"] >= near["residue_pairs"]
        assert set(near["per_residue_b"]) <= set(far["per_residue_b"])

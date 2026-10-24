"""Geometric interface contact analysis for run-one NY-ESO-1/HLA-A*02:01 binder designs.

Answers one question the ipSAE pass structurally cannot: does the designed binder
(chain D) engage the tumour-specific PEPTIDE (chain C, SLLMWITQC) or the INVARIANT
HLA-A*02:01 FRAMEWORK (chain A heavy chain, chain B beta-2-microglobulin)?

This is purely local geometry over the mirrored artifacts. No API calls, no spend.

Why this lives beside the layer-2 orchestrator rather than inside bindi:
  * ipSAE runs via ``layer2_orchestrator.py`` / ``layer2_core.py`` (container: ``--ipsae-only``).
    Keeping contact geometry separate avoids coupling the verified ipSAE path to campaign-specific
    interpretive rules.
  * bindi's ``parse_predicted_cif`` deliberately keeps only per-residue pLDDT and
    discards coordinates, so it cannot serve contacts; and the HLA alpha1/alpha2/alpha3
    region map below is campaign-specific knowledge, not a general scorer. If a future
    campaign needs region-aware contacts, promote ``contact_table`` into bindi then.

INTERPRETIVE RULE (the point of the whole file): raw contact counts are NOT
comparable between a 9-residue peptide and a 275-residue heavy chain. A 9-residue
chain is disadvantaged by construction, exactly as ipSAE is. The verdict is therefore
driven by WHETHER the solvent-exposed, TCR-facing peptide positions P4-P8 are touched
at all, and by whether heavy-chain contact falls on the groove-proximal helices or on
the alpha3 Ig domain / beta-2-microglobulin, which are nowhere near the peptide.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import gemmi
import numpy as np

BINDER_CHAIN = "D"
PEPTIDE_CHAIN = "C"
HEAVY_CHAIN = "A"
B2M_CHAIN = "B"

PEPTIDE_SEQUENCE = "SLLMWITQC"
TCR_FACING_POSITIONS = (4, 5, 6, 7, 8)
ANCHOR_POSITIONS = (2, 9)

CUTOFF_PRIMARY = 4.0
CUTOFF_SENSITIVITY = 5.0

# HLA-A*02:01 heavy chain regions, mature-protein numbering (CIF chain A is 1-275,
# beginning GSHSMRYFF..., i.e. standard mature numbering with no offset, as FLEET.toml
# [target.chain_A] numbering_note records).
#
# Domain boundaries follow FLEET.toml [target.chain_A] domains (alpha_1 1-90,
# alpha_2 91-182, alpha_3 183-274); within alpha_1/alpha_2 the helices are split from the
# beta-sheet groove floor because only the helices flank the peptide. alpha_3 is carried to
# 275 rather than 274 so the regions tile chain A exactly and no contacted residue can fall
# outside the map; residue 275 is the C-terminal residue and is in the alpha_3 Ig domain
# either way.
CHAIN_A_REGIONS: tuple[tuple[str, int, int], ...] = (
    ("groove_floor_beta_a1", 1, 56),
    ("alpha1_helix", 57, 84),
    ("a1_a2_linker", 85, 90),
    ("groove_floor_beta_a2", 91, 137),
    ("alpha2_helix", 138, 180),
    ("a2_a3_linker", 181, 182),
    ("alpha3_Ig", 183, 275),
)

GROOVE_PROXIMAL_REGIONS = frozenset(
    {"groove_floor_beta_a1", "alpha1_helix", "groove_floor_beta_a2", "alpha2_helix"}
)
PEPTIDE_REMOTE_REGIONS = frozenset({"alpha3_Ig"})


class ChainLayoutError(ValueError):
    """The CIF does not have the chain lettering/lengths this campaign assumes."""


EXPECTED_LAYOUT = {HEAVY_CHAIN: 275, B2M_CHAIN: 99, PEPTIDE_CHAIN: 9, BINDER_CHAIN: 73}


def region_of(seq_id: int) -> str:
    for name, lo, hi in CHAIN_A_REGIONS:
        if lo <= seq_id <= hi:
            return name
    return "out_of_range"


@dataclass(frozen=True)
class ChainAtoms:
    chain_id: str
    coords: np.ndarray          # (n_atoms, 3) heavy atoms only
    atom_seq_ids: np.ndarray    # (n_atoms,) residue seq id per atom
    residue_names: dict[int, str]

    @property
    def n_residues(self) -> int:
        return len(self.residue_names)


def load_chains(cif_path: str | Path) -> dict[str, ChainAtoms]:
    """Heavy-atom coordinates per chain from a Boltz ``_predicted.cif``.

    Hydrogens and deuteriums are excluded; waters/HETATM are excluded because Boltz
    predictions of this complex are polymer-only (asserted, not assumed).
    """
    st = gemmi.read_structure(str(cif_path))
    st.setup_entities()
    st.remove_alternative_conformations()
    st.remove_hydrogens()
    if len(st) < 1:
        raise ChainLayoutError(f"{cif_path}: no model in CIF")

    out: dict[str, ChainAtoms] = {}
    for chain in st[0]:
        coords: list[tuple[float, float, float]] = []
        seqs: list[int] = []
        names: dict[int, str] = {}
        for res in chain:
            names[res.seqid.num] = res.name
            for atom in res:
                el = atom.element.name
                if el in ("H", "D"):
                    continue
                coords.append((atom.pos.x, atom.pos.y, atom.pos.z))
                seqs.append(res.seqid.num)
        if not coords:
            continue
        out[chain.name] = ChainAtoms(
            chain_id=chain.name,
            coords=np.asarray(coords, dtype=float),
            atom_seq_ids=np.asarray(seqs, dtype=int),
            residue_names=names,
        )
    return out


def assert_layout(
    chains: dict[str, ChainAtoms],
    cif_path: str | Path,
    peptide_sequence: str | None = None,
) -> None:
    """Fail loudly rather than score the wrong interface if lettering differs.

    ``peptide_sequence`` is the chain-C sequence THIS structure is expected to carry,
    and defaults to the cognate PEPTIDE_SEQUENCE. A decoy refold is a deliberate
    chain-C variant, so scoring one requires passing ITS OWN expected sequence - not
    relaxing the check. The guard keeps its full strength either way: a structure
    whose chain C does not match what the caller expected still raises.
    """
    expected_peptide = PEPTIDE_SEQUENCE if peptide_sequence is None else peptide_sequence.upper()
    problems = []
    for cid, n in EXPECTED_LAYOUT.items():
        if cid not in chains:
            problems.append(f"chain {cid} absent (present: {sorted(chains)})")
        elif chains[cid].n_residues != n:
            problems.append(f"chain {cid} has {chains[cid].n_residues} residues, expected {n}")
    if PEPTIDE_CHAIN in chains:
        pep = chains[PEPTIDE_CHAIN]
        seq = gemmi.one_letter_code(
            [pep.residue_names[i] for i in sorted(pep.residue_names)]
        ).upper()
        if seq != expected_peptide:
            problems.append(f"chain {PEPTIDE_CHAIN} sequence {seq!r} != {expected_peptide!r}")
    if problems:
        raise ChainLayoutError(f"{cif_path}: " + "; ".join(problems))


def contacts(a: ChainAtoms, b: ChainAtoms, cutoff: float) -> dict:
    """Heavy-atom contacts between two chains at ``cutoff`` angstroms.

    Returns atom-atom pair count, residue-residue pair count, and per-residue
    atom-contact counts on each side. Atom pairs and residue pairs are both reported
    because atom pairs scale with buried area while residue pairs scale with interface
    breadth, and the two can disagree.
    """
    d = np.linalg.norm(a.coords[:, None, :] - b.coords[None, :, :], axis=-1)
    hit = d <= cutoff
    ai, bi = np.nonzero(hit)
    a_res = a.atom_seq_ids[ai]
    b_res = b.atom_seq_ids[bi]
    res_pairs = set(zip(a_res.tolist(), b_res.tolist()))

    per_a: dict[int, int] = {}
    for r in a_res.tolist():
        per_a[r] = per_a.get(r, 0) + 1
    per_b: dict[int, int] = {}
    for r in b_res.tolist():
        per_b[r] = per_b.get(r, 0) + 1

    return {
        "atom_pairs": int(hit.sum()),
        "residue_pairs": len(res_pairs),
        "n_residues_a": len(per_a),
        "n_residues_b": len(per_b),
        "per_residue_a": dict(sorted(per_a.items())),
        "per_residue_b": dict(sorted(per_b.items())),
        "min_distance": float(d.min()) if d.size else None,
    }


def peptide_breakdown(con: dict) -> dict:
    """Per-position P1-P9 contact counts, plus TCR-facing vs anchor rollup."""
    per_pos = {p: int(con["per_residue_b"].get(p, 0)) for p in range(1, 10)}
    return {
        "per_position_atom_contacts": per_pos,
        "positions_contacted": [p for p, v in per_pos.items() if v > 0],
        "tcr_facing_P4_P8_atom_contacts": sum(per_pos[p] for p in TCR_FACING_POSITIONS),
        "tcr_facing_P4_P8_positions_hit": [p for p in TCR_FACING_POSITIONS if per_pos[p] > 0],
        "anchor_P2_P9_atom_contacts": sum(per_pos[p] for p in ANCHOR_POSITIONS),
    }


def heavy_chain_breakdown(con: dict) -> dict:
    """Contacted chain A residues bucketed into alpha1/alpha2/groove floor/alpha3."""
    by_region: dict[str, int] = {name: 0 for name, _, _ in CHAIN_A_REGIONS}
    res_by_region: dict[str, list[int]] = {name: [] for name, _, _ in CHAIN_A_REGIONS}
    for seq_id, n in con["per_residue_b"].items():
        reg = region_of(int(seq_id))
        by_region.setdefault(reg, 0)
        res_by_region.setdefault(reg, [])
        by_region[reg] += int(n)
        res_by_region[reg].append(int(seq_id))
    total = sum(by_region.values())
    groove = sum(v for k, v in by_region.items() if k in GROOVE_PROXIMAL_REGIONS)
    remote = sum(v for k, v in by_region.items() if k in PEPTIDE_REMOTE_REGIONS)
    return {
        "atom_contacts_by_region": {k: v for k, v in by_region.items() if v > 0},
        "residues_by_region": {k: sorted(v) for k, v in res_by_region.items() if v},
        "groove_proximal_atom_contacts": groove,
        "alpha3_Ig_atom_contacts": remote,
        "groove_proximal_fraction_of_chainA": (groove / total) if total else None,
    }


PEPTIDE_DIRECTED_MIN_TCR_POSITIONS = 4
PEPTIDE_DIRECTED_MIN_TCR_ATOMS = 25
GROOVE_PROXIMAL_PURITY = 0.95


def classify(peptide: dict, chain_a: dict, b2m_atom_contacts: int) -> tuple[str, str, dict]:
    """Verdict for one design, by the stated interpretive rule.

    Driven by WHERE the binder sits, not by raw count ratios, because counts are not
    size-normalised. The tiers encode structural meaning:

      peptide-directed  - engages most of the solvent-exposed P4-P8 strip, and whatever
                          framework footing it takes is groove-proximal (alpha1/alpha2
                          helices, groove floor) with no alpha3 Ig or b2m contact. This
                          is the canonical TCR-like footprint.
      mixed             - genuine but partial or sparse P4-P8 engagement, or peptide
                          engagement alongside framework contact that reaches past the
                          groove.
      framework-directed - no contact to the P4-P8 strip at all. Dangerous rather than
                          weak, regardless of iptm.
    """
    tcr_hits = peptide["tcr_facing_P4_P8_positions_hit"]
    tcr_atoms = peptide["tcr_facing_P4_P8_atom_contacts"]
    any_peptide = bool(peptide["positions_contacted"])
    a3 = chain_a["alpha3_Ig_atom_contacts"]
    purity = chain_a["groove_proximal_fraction_of_chainA"]

    criteria = {
        "tcr_facing_positions_hit": len(tcr_hits),
        "tcr_facing_atom_contacts": tcr_atoms,
        "alpha3_Ig_atom_contacts": a3,
        "b2m_atom_contacts": b2m_atom_contacts,
        "groove_proximal_fraction_of_chainA": purity,
        "meets_tcr_position_breadth": len(tcr_hits) >= PEPTIDE_DIRECTED_MIN_TCR_POSITIONS,
        "meets_tcr_contact_depth": tcr_atoms >= PEPTIDE_DIRECTED_MIN_TCR_ATOMS,
        "no_peptide_remote_framework_contact": a3 == 0 and b2m_atom_contacts == 0,
        # purity is None when the binder makes no chain-A contact at all. That
        # is "no framework footing to assess", not "the footing is groove
        # proximal", and reading it as the latter put a criterion-met claim in
        # the verdict reason for a binder that never touched the framework.
        "framework_footing_is_groove_proximal": (
            None if purity is None else purity >= GROOVE_PROXIMAL_PURITY
        ),
        "framework_footing_assessable": purity is not None,
    }

    if not any_peptide:
        return (
            "framework-directed",
            "no heavy-atom contact to any peptide position; the binder does not touch "
            "the only tumour-specific surface in the complex",
            criteria,
        )
    if not tcr_hits:
        return (
            "framework-directed",
            "peptide contact exists but none of it is on the solvent-exposed P4-P8 strip "
            f"(only positions {peptide['positions_contacted']}), so it is groove-rim "
            "proximity rather than peptide readout",
            criteria,
        )
    if all(
        criteria[k]
        for k in (
            "meets_tcr_position_breadth",
            "meets_tcr_contact_depth",
            "no_peptide_remote_framework_contact",
            "framework_footing_is_groove_proximal",
        )
    ):
        return (
            "peptide-directed",
            f"engages {len(tcr_hits)} of 5 TCR-facing positions {tcr_hits} with {tcr_atoms} "
            "heavy-atom contacts; all framework contact is groove-proximal "
            "(alpha1/alpha2 helices and groove floor) with zero alpha3 Ig and zero b2m "
            "contact - the canonical TCR-like footprint",
            criteria,
        )
    if a3 or b2m_atom_contacts:
        return (
            "mixed (framework reach beyond groove)",
            f"touches TCR-facing positions {tcr_hits} but also makes {a3} alpha3 Ig and "
            f"{b2m_atom_contacts} b2m contacts, which are nowhere near the peptide",
            criteria,
        )
    return (
        "mixed (peptide-marginal)",
        f"touches only TCR-facing positions {tcr_hits} with {tcr_atoms} heavy-atom "
        "contacts; peptide engagement is present and groove-proximal but too sparse or "
        "narrow to call a full readout",
        criteria,
    )


def analyse_design(
    design_id: str,
    cif_path: Path,
    cutoffs=(CUTOFF_PRIMARY, CUTOFF_SENSITIVITY),
    peptide_sequence: str | None = None,
) -> dict:
    chains = load_chains(cif_path)
    assert_layout(chains, cif_path, peptide_sequence)
    binder = chains[BINDER_CHAIN]

    rec: dict = {"design_id": design_id, "cif": cif_path.name,
                 "chain_residue_counts": {c: chains[c].n_residues for c in sorted(chains)},
                 "binder_heavy_atoms": int(binder.coords.shape[0]), "cutoffs": {}}

    for cutoff in cutoffs:
        per_partner = {}
        for partner in (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN):
            per_partner[partner] = contacts(binder, chains[partner], cutoff)
        total_atoms = sum(v["atom_pairs"] for v in per_partner.values())
        total_respairs = sum(v["residue_pairs"] for v in per_partner.values())
        entry = {
            "atom_pairs": {k: v["atom_pairs"] for k, v in per_partner.items()},
            "residue_pairs": {k: v["residue_pairs"] for k, v in per_partner.items()},
            "min_distance": {k: v["min_distance"] for k, v in per_partner.items()},
            "binder_residues_in_interface": {
                k: v["n_residues_a"] for k, v in per_partner.items()
            },
            "total_interface_atom_pairs": total_atoms,
            "peptide_fraction_of_atom_contacts": (
                per_partner[PEPTIDE_CHAIN]["atom_pairs"] / total_atoms if total_atoms else None
            ),
            "peptide_fraction_of_residue_pairs": (
                per_partner[PEPTIDE_CHAIN]["residue_pairs"] / total_respairs
                if total_respairs else None
            ),
            "peptide": peptide_breakdown(per_partner[PEPTIDE_CHAIN]),
            "chain_A": heavy_chain_breakdown(per_partner[HEAVY_CHAIN]),
            "b2m_atom_contacts": per_partner[B2M_CHAIN]["atom_pairs"],
            "b2m_residues_contacted": sorted(
                int(k) for k in per_partner[B2M_CHAIN]["per_residue_b"]
            ),
        }
        rec["cutoffs"][f"{cutoff:.1f}"] = entry

    primary = rec["cutoffs"][f"{CUTOFF_PRIMARY:.1f}"]
    verdict, reason, criteria = classify(
        primary["peptide"], primary["chain_A"], primary["b2m_atom_contacts"]
    )
    rec["verdict"] = verdict
    rec["verdict_reason"] = reason
    rec["verdict_criteria"] = criteria
    return rec


def buried_area(cif_path: Path) -> dict | None:
    """Buried surface area per partner, via biotite's Shrake-Rupley SASA.

    Two numbers, because they answer different questions and can disagree:

    ``pairwise`` - BSA(D,X) = (SASA(D) + SASA(X) - SASA(D+X)) / 2, each chain taken in
    isolation. This is the classic pairwise interface area, but for the peptide it
    overstates the physiological burial: an isolated 9-mer exposes its groove-facing
    face, which is not available in situ.

    ``complex_context`` - the SASA each chain loses when D is added to the assembled
    A+B+C complex. For the peptide this is the right number: how much of the strip that
    is actually solvent-exposed in the pMHC gets covered by the binder.

    Both are computed on the predicted geometry with no repacking, so they are
    rigid-body contact areas, not binding free energies. Returns None if biotite is
    unavailable, so the caller can say SKIPPED rather than invent a proxy.
    """
    try:
        import biotite.structure as struc
        import biotite.structure.io.pdbx as pdbx
    except ImportError:
        return None

    f = pdbx.CIFFile.read(str(cif_path))
    arr = pdbx.get_structure(f, model=1)
    arr = arr[struc.filter_amino_acids(arr) & (arr.element != "H")]

    def per_atom(mask) -> np.ndarray:
        return struc.sasa(arr[mask], vdw_radii="Single", point_number=200)

    def total(mask) -> float:
        return float(np.nansum(per_atom(mask)))

    d_mask = arr.chain_id == BINDER_CHAIN
    pmhc_mask = np.isin(arr.chain_id, [HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN])
    sasa_d = total(d_mask)

    # complex-context: per-chain SASA within A+B+C, then within A+B+C+D
    def chain_sasa_within(mask) -> dict[str, float]:
        sub = arr[mask]
        vals = struc.sasa(sub, vdw_radii="Single", point_number=200)
        return {
            c: float(np.nansum(vals[sub.chain_id == c]))
            for c in (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN)
        }

    in_pmhc = chain_sasa_within(pmhc_mask)
    in_full = chain_sasa_within(pmhc_mask | d_mask)

    pairwise: dict[str, float] = {}
    for partner in (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN):
        p_mask = arr.chain_id == partner
        if not p_mask.any():
            continue
        pairwise[partner] = round((sasa_d + total(p_mask) - total(d_mask | p_mask)) / 2.0, 1)

    return {
        "pairwise": pairwise,
        "complex_context_delta_sasa_on_binding": {
            c: round(in_pmhc[c] - in_full[c], 1) for c in in_pmhc
        },
        "available_sasa_in_pmhc": {c: round(in_pmhc[c], 1) for c in in_pmhc},
        # The size-normalised answer: of the surface each chain actually exposes in the
        # assembled pMHC, what fraction does the binder cover? This is the one measure
        # in the whole analysis that is immune to the 9-vs-275 residue asymmetry that
        # biases ipSAE and raw contact counts alike.
        "fraction_of_available_surface_buried": {
            c: (round((in_pmhc[c] - in_full[c]) / in_pmhc[c], 4) if in_pmhc[c] > 0 else None)
            for c in in_pmhc
        },
        "_method": (
            "biotite.structure.sasa (Shrake-Rupley), Single vdw radii, 200 test points; "
            "freesasa was not usable on this box (wheel fails to build on Python 3.13)"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", default=str(Path(__file__).parent / "artifacts"))
    ap.add_argument("--out", default=None, help="write JSON here (default: stdout only)")
    ap.add_argument("--bsa", action="store_true", help="also compute buried surface area")
    args = ap.parse_args(argv)

    root = Path(args.artifacts)
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        cif = d / f"{d.name}_predicted.cif"
        if not cif.exists():
            errors[d.name] = "missing _predicted.cif"
            continue
        try:
            rec = analyse_design(d.name, cif)
            if args.bsa:
                bsa = buried_area(cif)
                rec["buried_surface_area_A2"] = bsa if bsa else "SKIPPED: biotite unavailable"
            results[d.name] = rec
        except Exception as e:
            errors[d.name] = f"{type(e).__name__}: {e}"

    payload = {
        "method": {
            "contacts": "heavy-atom (hydrogens excluded) inter-chain distance <= cutoff",
            "cutoff_primary_angstrom": CUTOFF_PRIMARY,
            "cutoff_sensitivity_angstrom": CUTOFF_SENSITIVITY,
            "chain_map": {
                HEAVY_CHAIN: "HLA-A*02:01 heavy chain (invariant)",
                B2M_CHAIN: "beta-2-microglobulin (invariant)",
                PEPTIDE_CHAIN: f"peptide {PEPTIDE_SEQUENCE} (tumour-specific)",
                BINDER_CHAIN: "designed binder",
            },
            "chain_A_regions": {n: [lo, hi] for n, lo, hi in CHAIN_A_REGIONS},
            "interpretive_rule": (
                "Raw contact counts are not size-normalised; a 9-residue peptide is "
                "disadvantaged against a 275-residue chain by construction. Verdicts are "
                "therefore driven by whether the solvent-exposed TCR-facing P4-P8 strip is "
                "engaged at all, not by count ratios. Zero P4-P8 contact is "
                "framework-directed regardless of iptm."
            ),
            "caveats": [
                "Geometry from a predicted structure, not an experimental one; contact "
                "counts inherit all of Boltz's modelling error.",
                "Contact counts and BSA are descriptive, not calibrated affinity or "
                "specificity measures, and remain NON-GATING.",
                "Specificity cannot be established by any single-complex analysis: it "
                "requires counter-screening the same HLA presenting irrelevant peptides. "
                "The MAGE-A3 a3a / titin cardiac deaths are the standing reminder that a "
                "framework-directed binder is dangerous, not merely weak.",
            ],
        },
        "designs": results,
        "errors": errors,
    }
    text = json.dumps(payload, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

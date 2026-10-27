"""Tier 0 targeting metrics for run-one, per UPGRADES.md section 4 items 1-4.

These are the four quantities UPGRADES.md marks as computable today at zero spend from
artifacts already on disk. They are implemented here as RECORDED-NON-GATING measurements.

NOTHING IN THIS FILE IS A GATE. UPGRADES.md states in its own header that it changes no
gate in ``FLEET.toml``, and marks items 1-3 as "GATING, proposed" - proposals needing the
user's decision. Section 7 records that no calibrated threshold exists for any of them.
This module therefore computes and records; it does not pass or fail a design.

Also hosts the shell-cutoff sweep formerly in ``shell_sweep.py``:
``python tier0_targeting.py sweep``. Diagnostic only — see UPGRADES.md section 9 / F1.

Relationship to ``contact_analysis.py``, which already lives in this directory:

  ``contact_analysis.py`` answers DOCKING SITE under a campaign-specific interpretive rule
  (is the P4-P8 strip touched, is framework footing groove-proximal). It is OURS.

  This file implements the BindCraft2 G7 definitions instead, which are different
  quantities computed differently: a hotspot-DERIVED epitope shell, and ratios of
  CONTACTED RESIDUES rather than atom-contact counts. The point of adopting the
  teacher's definitions verbatim is that the metric is then inherited rather than
  invented, while the thresholds are explicitly not inherited (G7 Teacher's setting:
  ``max_off_epitope_contact_final`` and ``min_hotspot_contact_final`` have no default
  value in the source, so the gates are opt-in per campaign).

  Both read the same coordinates and reuse ``contact_analysis``'s loader and its chain
  layout assertion, so the two cannot silently diverge on which structures they scored.

What each number is and is not evidence of (UPGRADES.md section 4):

  off_epitope_contact_fraction   evidence of WHERE CONTACT FELL.
                                 NOT evidence that on-epitope contact is favourable.
  coldspot_contact_fraction      evidence of engagement of surface we declared off-limits.
                                 NOT evidence of affinity, or of its absence.
  buried_anchor_contact_count    evidence of a physically impossible or mis-modelled pose.
                                 NOT evidence of selectivity.
  invariant_surface_fraction     evidence of framework engagement, i.e. the hazard named in
                                 UPGRADES.md section 2.
                                 NOT evidence of peptide specificity.
  peptide_burial_fraction        peptide share of binder buried surface (CORRECT pose
                                 pre-registered readout). Report-only; no threshold.
                                 Distinguishes peptide-directed burial from groove affinity.
  hotspot_contact_fraction       ALSO the BoltzGen issue #215 honour check: after a re-run
                                 with narrowed epitope / non_binding on the wire, a still-
                                 near-zero value means the hosted service likely ignored the
                                 fields; a rise that still leaves burial on the groove means
                                 the fields were honoured but did not help. Report-only.

G6 audit - which projection losses these depend on: NONE. These are computed on full 3D
heavy-atom coordinates, not on the G1 cylindrical projection, so no azimuthal, truncation
or bin-quantisation loss applies. They do inherit the predictor's coordinate error, which
is a different and separately recorded limitation.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

from contact_analysis import (
    B2M_CHAIN,
    BINDER_CHAIN,
    HEAVY_CHAIN,
    PEPTIDE_CHAIN,
    ChainAtoms,
    assert_layout,
    load_chains,
)

FLAGS_PATH = Path(__file__).resolve().parent.parent / "targeting_flags.json"


def load_flags(path: Path = FLAGS_PATH) -> dict:
    return json.loads(path.read_text())


def _expand_ranges(ranges) -> set[int]:
    out: set[int] = set()
    for lo, hi in ranges:
        out.update(range(int(lo), int(hi) + 1))
    return out


def hotspot_atom_mask(chains: dict[str, ChainAtoms], flags: dict) -> dict[str, np.ndarray]:
    """Per-chain boolean atom masks selecting the declared hotspot residues."""
    masks: dict[str, np.ndarray] = {}
    for cid, positions in flags["hotspots"].items():
        if cid.startswith("_"):
            continue
        ch = chains[cid]
        masks[cid] = np.isin(ch.atom_seq_ids, np.asarray(positions, dtype=int))
    return masks


def epitope_shell(
    chains: dict[str, ChainAtoms], flags: dict, target_chains: tuple[str, ...]
) -> dict[str, set[int]]:
    """Target residues within the shell cutoff of ANY hotspot atom.

    Minimum heavy-atom to heavy-atom distance, exactly as BindCraft2
    ``epitope_targeting.py:25-29`` defines it. The shell is DERIVED, never declared:
    a single statement of which residues matter generates both the positive and the
    negative criterion (G7 Principle).
    """
    cutoff = float(flags["epitope_shell_cutoff_angstrom"])
    hs_masks = hotspot_atom_mask(chains, flags)
    hs_coords = np.concatenate(
        [chains[c].coords[m] for c, m in hs_masks.items() if m.any()], axis=0
    )

    shell: dict[str, set[int]] = {}
    for cid in target_chains:
        ch = chains[cid]
        d = np.linalg.norm(ch.coords[:, None, :] - hs_coords[None, :, :], axis=-1)
        within = d.min(axis=1) <= cutoff
        shell[cid] = {int(r) for r in np.unique(ch.atom_seq_ids[within])}
    return shell


def contacted_residues(
    binder: ChainAtoms, target: ChainAtoms, cutoff: float
) -> set[int]:
    """Target residues with at least one heavy atom within ``cutoff`` of the binder."""
    d = np.linalg.norm(binder.coords[:, None, :] - target.coords[None, :, :], axis=-1)
    hit = (d <= cutoff).any(axis=0)
    return {int(r) for r in np.unique(target.atom_seq_ids[hit])}


def coldspot_set(
    chains: dict[str, ChainAtoms], flags: dict, shell: dict[str, set[int]]
) -> dict[str, set[int]]:
    """The declared coldspot residues, resolved against this structure's numbering.

    The alpha1/alpha2 helix contribution is helix-minus-shell, which is why the coldspot
    set depends on the shell cutoff. ``targeting_flags.json`` records that this definition
    of 'rim' is unresolved.
    """
    spec = flags["coldspots"]
    out: dict[str, set[int]] = {}

    if spec.get("B") == "all":
        out[B2M_CHAIN] = set(chains[B2M_CHAIN].residue_names)

    a_resids = set(chains[HEAVY_CHAIN].residue_names)
    cold_a = _expand_ranges(spec.get("A_ranges", [])) & a_resids
    helix = _expand_ranges(spec.get("A_helix_ranges_minus_shell", [])) & a_resids
    cold_a |= helix - shell.get(HEAVY_CHAIN, set())
    out[HEAVY_CHAIN] = cold_a
    return out


def invariant_surface_fraction(cif_path: Path, flags: dict) -> dict | None:
    """Fraction of the INVARIANT surface the binder buries (UPGRADES.md item 4).

    Invariant surface is taken as chains A and B TOGETHER, not per chain, because the
    hazard in UPGRADES.md section 2 is about the invariant body as a whole. The denominator
    is the SASA those chains actually expose in the assembled pMHC, which is the only
    size-normalised form of the question.

    Shrake-Rupley over the predicted geometry with no repacking: a rigid-body contact area,
    not a binding free energy. Returns None if biotite is unavailable so the caller can
    report SKIPPED rather than substitute a proxy.
    """
    try:
        import biotite.structure as struc
        import biotite.structure.io.pdbx as pdbx
    except ImportError:
        return None

    f = pdbx.CIFFile.read(str(cif_path))
    arr = pdbx.get_structure(f, model=1)
    arr = arr[struc.filter_amino_acids(arr) & (arr.element != "H")]

    inv = list(flags["invariant_surface_chains"])
    dis = list(flags["discriminating_surface_chains"])
    pmhc = np.isin(arr.chain_id, inv + dis)
    d_mask = arr.chain_id == BINDER_CHAIN

    def group_sasa(subset_mask, group) -> float:
        sub = arr[subset_mask]
        vals = struc.sasa(sub, vdw_radii="Single", point_number=200)
        return float(np.nansum(vals[np.isin(sub.chain_id, group)]))

    inv_before = group_sasa(pmhc, inv)
    inv_after = group_sasa(pmhc | d_mask, inv)
    dis_before = group_sasa(pmhc, dis)
    dis_after = group_sasa(pmhc | d_mask, dis)

    return {
        "invariant_chains": inv,
        "invariant_available_sasa_A2": round(inv_before, 1),
        "invariant_buried_A2": round(inv_before - inv_after, 1),
        "invariant_surface_fraction": (
            round((inv_before - inv_after) / inv_before, 5) if inv_before > 0 else None
        ),
        "discriminating_available_sasa_A2": round(dis_before, 1),
        "discriminating_buried_A2": round(dis_before - dis_after, 1),
        "discriminating_surface_fraction": (
            round((dis_before - dis_after) / dis_before, 5) if dis_before > 0 else None
        ),
        "_method": (
            "biotite.structure.sasa (Shrake-Rupley), Single vdw radii, 200 test points, "
            "heavy atoms only; invariant chains pooled before the ratio is taken"
        ),
    }


# Bondi radii + Shrake-Rupley constants for peptide_burial_fraction. Kept local so
# the metric does not depend on biotite (absent from the pinned image) and matches
# /workspace/interface_geometry/analyse.py exactly.
_BONDI = {"C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80, "SE": 1.90}
_PROBE = 1.4
_N_SPHERE = 256


def _sphere_points(n: int = _N_SPHERE) -> np.ndarray:
    import math

    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5**0.5) * i
    return np.stack(
        [np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], axis=1
    )


_SPHERE = _sphere_points()


def _sasa_per_atom(coords: np.ndarray, radii: np.ndarray) -> np.ndarray:
    """Shrake-Rupley per-atom SASA (A^2)."""
    import math

    r = radii + _PROBE
    out = np.zeros(len(coords))
    for i in range(len(coords)):
        d = np.linalg.norm(coords - coords[i], axis=1)
        nb = np.where((d < r + r[i]) & (d > 0))[0]
        pts = coords[i] + _SPHERE * r[i]
        if len(nb):
            dd = np.linalg.norm(pts[:, None, :] - coords[nb][None, :, :], axis=2)
            acc = ~(dd < r[nb][None, :]).any(1)
        else:
            acc = np.ones(_N_SPHERE, dtype=bool)
        out[i] = 4 * math.pi * r[i] ** 2 * acc.sum() / _N_SPHERE
    return out


def peptide_burial_fraction(cif_path: Path) -> dict:
    """Peptide share of binder buried surface. Pre-registered readout, not a gate.

    Method (stated so a re-run is reproducible; identical to interface_geometry):
      * heavy atoms only
      * Shrake-Rupley, probe 1.4 A, 256 sphere points, Bondi radii
      * burial of binder against a partner = SASA(D alone) - SASA(D in D+partner)
      * fraction = burial_vs_peptide / burial_vs_A+B+C

    Returns None-valued fields rather than raising when a chain is missing, so the
    orchestrator can record the gap. No threshold is applied anywhere.
    """
    import gemmi

    st = gemmi.read_structure(str(cif_path))
    st.setup_entities()
    st.remove_hydrogens()
    chains: dict[str, tuple[np.ndarray, list]] = {}
    for c in st[0]:
        coords, info = [], []
        for res in c:
            for atom in res:
                el = atom.element.name.upper()
                if el in ("H", "D"):
                    continue
                coords.append([atom.pos.x, atom.pos.y, atom.pos.z])
                info.append((res.seqid.num, res.name, el))
        if coords:
            chains[c.name] = (np.asarray(coords, dtype=float), info)

    needed = (BINDER_CHAIN, HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN)
    missing = [c for c in needed if c not in chains]
    if missing:
        return {
            "peptide_burial_fraction": None,
            "skipped": f"missing chains {missing}",
            "method": (
                "Shrake-Rupley probe 1.4 A, 256 points, Bondi radii; "
                "burial = SASA(D alone) - SASA(D in D+partner)"
            ),
        }

    def _radii(info):
        return np.array([_BONDI.get(e, 1.70) for _, _, e in info])

    def sasa_of_D(partners: tuple[str, ...]) -> float:
        co = [chains[BINDER_CHAIN][0]]
        inf = list(chains[BINDER_CHAIN][1])
        for p in partners:
            co.append(chains[p][0])
            inf.extend(chains[p][1])
        stacked = np.vstack(co)
        s = _sasa_per_atom(stacked, _radii(inf))
        return float(s[: len(chains[BINDER_CHAIN][0])].sum())

    free = sasa_of_D(())
    with_pep = sasa_of_D((PEPTIDE_CHAIN,))
    with_all = sasa_of_D((HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN))
    buried_pep = free - with_pep
    buried_total = free - with_all
    frac = (buried_pep / buried_total) if buried_total > 1e-6 else None
    return {
        "peptide_burial_fraction": None if frac is None else round(frac, 5),
        "binder_sasa_free_A2": round(free, 2),
        "binder_buried_vs_peptide_A2": round(buried_pep, 2),
        "binder_buried_total_A2": round(buried_total, 2),
        "method": (
            "Shrake-Rupley probe 1.4 A, 256 points, Bondi radii; "
            "burial = SASA(D alone) - SASA(D in D+partner); "
            "fraction = burial_vs_C / burial_vs_A+B+C"
        ),
        "control_distribution": {
            "min": 0.0,
            "max": 0.419,
            "note": (
                "pre-registered 2026-10-27 from interface_geometry; "
                "report-only, not a bar"
            ),
        },
        "gate": False,
    }



def analyse_design(
    design_id: str,
    cif_path: Path,
    flags: dict,
    with_sasa: bool = True,
    peptide_sequence: str | None = None,
) -> dict:
    chains = load_chains(cif_path)
    assert_layout(chains, cif_path, peptide_sequence)

    cutoff = float(flags["contact_cutoff_angstrom"])
    target_chains = (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN)
    binder = chains[BINDER_CHAIN]

    shell = epitope_shell(chains, flags, target_chains)
    cold = coldspot_set(chains, flags, shell)

    contacted = {c: contacted_residues(binder, chains[c], cutoff) for c in target_chains}
    n_contacted_total = sum(len(v) for v in contacted.values())

    in_shell = sum(len(contacted[c] & shell[c]) for c in target_chains)
    off_shell = n_contacted_total - in_shell

    hotspots = {
        c: set(v) for c, v in flags["hotspots"].items() if not c.startswith("_")
    }
    n_hotspots = sum(len(v) for v in hotspots.values())
    hotspots_hit = sum(len(contacted[c] & v) for c, v in hotspots.items())

    n_cold = sum(len(v) for v in cold.values())
    cold_hit = sum(len(contacted[c] & v) for c, v in cold.items())

    anchors = {
        c: set(v) for c, v in flags["buried_anchors"].items() if not c.startswith("_")
    }
    anchor_hit = sorted(
        r for c, v in anchors.items() for r in (contacted[c] & v)
    )

    rec: dict = {
        "design_id": design_id,
        "cif": cif_path.name,
        "item_1_off_epitope_contact_fraction": (
            round(off_shell / n_contacted_total, 5) if n_contacted_total else None
        ),
        "item_2_coldspot_contact_fraction": (
            round(cold_hit / n_cold, 5) if n_cold else None
        ),
        # A binder that contacted nothing has no measured anchor count: len([])
        # is 0, and 0 is also the PASSING value of the hard gate. Report None,
        # the way the sibling fractions above already do, so "touched nothing"
        # cannot read as "cleanly avoided the buried anchors".
        "item_3_buried_anchor_contact_count": (
            len(anchor_hit) if n_contacted_total else None
        ),
        "hotspot_contact_fraction": (
            round(hotspots_hit / n_hotspots, 5) if n_hotspots else None
        ),
        "counts": {
            "contacted_target_residues": n_contacted_total,
            "contacted_in_epitope_shell": in_shell,
            "contacted_off_epitope_shell": off_shell,
            "hotspots_declared": n_hotspots,
            "hotspots_contacted": hotspots_hit,
            "coldspots_declared": n_cold,
            "coldspots_contacted": cold_hit,
            "epitope_shell_size_by_chain": {c: len(shell[c]) for c in target_chains},
            "contacted_by_chain": {c: sorted(contacted[c]) for c in target_chains},
            "coldspots_contacted_by_chain": {
                c: sorted(contacted[c] & v) for c, v in cold.items() if contacted[c] & v
            },
            "buried_anchor_residues_contacted": anchor_hit,
        },
    }

    if with_sasa:
        sasa = invariant_surface_fraction(cif_path, flags)
        rec["item_4_invariant_surface"] = (
            sasa if sasa else "SKIPPED: biotite unavailable; no proxy substituted"
        )
        # Pre-registered CORRECT pose readout. Independent of biotite; always computed
        # when SASA is requested. Report-only - see FLEET.toml [pre_registered_readouts].
        rec["peptide_burial_fraction"] = peptide_burial_fraction(cif_path)
    return rec



DEFAULT_SWEEP_CUTOFFS = (4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0)


def item1_reporting_at_shell(
    cif_path: Path,
    flags: dict,
    shell_angstrom: float,
    peptide_sequence: str | None = None,
) -> dict:
    """Item 1 off-epitope fraction at an explicit shell (P1 dual reporting; not a gate)."""
    row = sweep_design(cif_path, flags, (shell_angstrom,), peptide_sequence)["by_cutoff"][
        f"{shell_angstrom:.1f}"
    ]
    return {
        "reporting_shell_angstrom": shell_angstrom,
        "item_1_off_epitope_contact_fraction": row["off_epitope_contact_fraction"],
        "epitope_shell_size_by_chain": row["shell_size_by_chain"],
        "epitope_shell_size_total": row["shell_size_total"],
    }


def sweep_design(
    cif_path: Path,
    flags: dict,
    cutoffs=DEFAULT_SWEEP_CUTOFFS,
    peptide_sequence: str | None = None,
) -> dict:
    """Off-epitope contact fraction at each shell cutoff. Diagnostic only — not a gate."""
    chains = load_chains(cif_path)
    assert_layout(chains, cif_path, peptide_sequence)
    binder = chains[BINDER_CHAIN]
    target_chains = (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN)
    contact_cutoff = float(flags["contact_cutoff_angstrom"])

    contacted = {c: contacted_residues(binder, chains[c], contact_cutoff) for c in target_chains}
    n_contacted = sum(len(v) for v in contacted.values())

    out: dict[str, dict] = {}
    for cut in cutoffs:
        shell = epitope_shell(chains, {**flags, "epitope_shell_cutoff_angstrom": cut}, target_chains)
        in_shell = sum(len(contacted[c] & shell[c]) for c in target_chains)
        out[f"{cut:.1f}"] = {
            "off_epitope_contact_fraction": (
                round((n_contacted - in_shell) / n_contacted, 5) if n_contacted else None
            ),
            "shell_size_by_chain": {c: len(shell[c]) for c in target_chains},
            "shell_size_total": sum(len(shell[c]) for c in target_chains),
        }
    return {"contacted_target_residues": n_contacted, "by_cutoff": out}


def main_sweep(argv: list[str] | None = None) -> int:
    """Former shell_sweep.py entry point. Invoked as: python tier0_targeting.py sweep ..."""
    ap = argparse.ArgumentParser(
        prog="tier0_targeting.py sweep",
        description=(
            "Shell-cutoff sweep for UPGRADES.md item 1. Diagnostic only — does not choose a "
            "cutoff, rank designs, or gate."
        ),
    )
    ap.add_argument("--artifacts", default=str(Path(__file__).parent / "artifacts"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    flags = load_flags(FLAGS_PATH)
    root = Path(args.artifacts)
    per_design: dict[str, dict] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        cif = d / f"{d.name}_predicted.cif"
        if cif.exists():
            per_design[d.name] = sweep_design(cif, flags, DEFAULT_SWEEP_CUTOFFS)

    summary: dict[str, dict] = {}
    for cut in DEFAULT_SWEEP_CUTOFFS:
        key = f"{cut:.1f}"
        vals = [v["by_cutoff"][key]["off_epitope_contact_fraction"] for v in per_design.values()]
        vals = [v for v in vals if v is not None]
        shells = [v["by_cutoff"][key]["shell_size_total"] for v in per_design.values()]
        # Every value can be None at a given cutoff (no design contacted the
        # target). min/median would raise on the empty list; report the absence.
        summary[key] = {
            "off_epitope_min": round(min(vals), 5) if vals else None,
            "off_epitope_max": round(max(vals), 5) if vals else None,
            "off_epitope_median": round(statistics.median(vals), 5) if vals else None,
            "off_epitope_stdev": round(statistics.pstdev(vals), 5) if vals else None,
            "designs_measured": len(vals),
            "designs_at_zero": sum(1 for v in vals if v == 0.0),
            "shell_size_total_min": min(shells) if shells else None,
            "shell_size_total_max": max(shells) if shells else None,
        }

    payload = {
        "status": "DIAGNOSTIC - not a selection, not a gate",
        "question": (
            "Is there a shell cutoff at which off-epitope contact fraction has enough spread "
            "across designs to discriminate at all? At the teacher's 10.0 A it does not."
        ),
        "warning": (
            "Choosing a cutoff by the spread it maximises on these ten designs would fit a "
            "free parameter to the campaign's own output. Any cutoff adopted must be argued "
            "structurally and pre-registered BEFORE the next run, per UPGRADES.md section 4."
        ),
        "contact_cutoff_angstrom": flags["contact_cutoff_angstrom"],
        "hotspots": {k: v for k, v in flags["hotspots"].items() if not k.startswith("_")},
        "summary_by_shell_cutoff": summary,
        "designs": per_design,
    }
    text = json.dumps(payload, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text)
    print(json.dumps(summary, indent=1))
    return 0


def manifest_payload(
    flags: dict,
    flags_path: Path,
    designs: dict[str, dict],
    errors: dict[str, str],
) -> dict:
    """Tier 0 manifest + per-design rows (also embedded in ``layer2_bundle.json``)."""
    return {
        "status": "RECORDED-NON-GATING",
        "spec": "UPGRADES.md v1.0 section 4, Tier 0 items 1-4",
        "gating_warning": (
            "No threshold is applied anywhere in this file. UPGRADES.md marks items 1-3 as "
            "'GATING, proposed' and section 7 records that no calibrated threshold exists "
            "for any item. Gating descriptors remain iptm and plddt only; FLEET.toml is "
            "untouched."
        ),
        "parameters": {
            "epitope_shell_cutoff_angstrom": flags["epitope_shell_cutoff_angstrom"],
            "contact_cutoff_angstrom": flags["contact_cutoff_angstrom"],
            "hotspots": {k: v for k, v in flags["hotspots"].items() if not k.startswith("_")},
            "buried_anchors": {
                k: v for k, v in flags["buried_anchors"].items() if not k.startswith("_")
            },
            "coldspot_definition": flags["coldspots"]["_definition"],
            "flags_file": str(flags_path.name),
        },
        "provenance": {
            "off_epitope_contact_fraction": "BindCraft2 filters.py:423-432",
            "coldspot_contact_fraction": "BindCraft2 filters.py:219-227",
            "hotspot_contact_fraction": (
                "BindCraft2 filters.py:209-217; ALSO BoltzGen issue #215 honour "
                "check for whether epitope_residues / non_binding_residues were "
                "honoured by the hosted service (CORRECT pose 2026-10-27)"
            ),
            "epitope_shell": "BindCraft2 epitope_targeting.py:25-29, EPITOPE_CUTOFF=10.0",
            "buried_anchor_contact_count": "OURS (UPGRADES.md item 3)",
            "invariant_surface_fraction": "OURS (UPGRADES.md item 4)",
            "peptide_burial_fraction": (
                "OURS (CORRECT pose 2026-10-27); Shrake-Rupley probe 1.4 A, "
                "256 points, Bondi; same method as interface_geometry/analyse.py; "
                "pre-registered control 0.0-0.419; report-only, not a gate"
            ),
        },
        "caveats": [
            "Predicted coordinates, not experimental; every number inherits the predictor's "
            "error, and contact tests are sensitive to side-chain placement.",
            "The fractions are only as good as the flags: a mis-assigned hotspot produces a "
            "confident number measuring the wrong thing (G7 Limits).",
            "The 10.0 A shell cutoff is a free parameter with no calibration behind it. On a "
            "9-residue discriminating surface the shell reaches well into the invariant "
            "helices, which makes a LOW off-epitope fraction easier to achieve than it reads.",
            "Nothing here says a contact is favourable; it says only where contact fell.",
            "The coldspot definition is unresolved - see _coldspot_ambiguity in the flags file.",
            "hotspot_contact_fraction after a re-run with narrowed targeting is the "
            "BoltzGen #215 honour check: near-zero on most draws means the fields were "
            "likely ignored; do not read a low value as 'did not help' without that check.",
            "peptide_burial_fraction is pre-registered and report-only. The 0.0-0.419 "
            "control is a distribution to compare against, not a threshold.",
        ],
        "designs": designs,
        "errors": errors,
    }


def main_measure(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tier 0 targeting metrics (recorded, non-gating)")
    ap.add_argument("--artifacts", default=str(Path(__file__).parent / "artifacts"))
    ap.add_argument("--flags", default=str(FLAGS_PATH))
    ap.add_argument(
        "--out",
        default=None,
        help="optional JSON path; canonical store is artifacts/layer2_bundle.json (orchestrator)",
    )
    ap.add_argument("--no-sasa", action="store_true")
    args = ap.parse_args(argv)

    flags = load_flags(Path(args.flags))
    root = Path(args.artifacts)
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        cif = d / f"{d.name}_predicted.cif"
        if not cif.exists():
            errors[d.name] = "missing _predicted.cif"
            continue
        try:
            results[d.name] = analyse_design(
                d.name, cif, flags, with_sasa=not args.no_sasa
            )
        except Exception as e:  # noqa: BLE001 - record, do not mask
            errors[d.name] = f"{type(e).__name__}: {e}"

    payload = manifest_payload(flags, Path(args.flags), results, errors)
    text = json.dumps(payload, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    """Dispatch: ``sweep`` subcommand, otherwise the Tier 0 measure (legacy CLI)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "sweep":
        return main_sweep(argv[1:])
    return main_measure(argv)


if __name__ == "__main__":
    sys.exit(main())

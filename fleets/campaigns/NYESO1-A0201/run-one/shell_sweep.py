"""Shell-cutoff sweep for UPGRADES.md item 1 (off-epitope contact fraction).

WHY THIS EXISTS. The Tier 0 run at the teacher's 10.0 A shell produced an off-epitope
contact fraction of 0.000-0.111 across all ten run-one designs, with eight at or near zero.
That is not a good score; it is a non-measurement. G7's Limits field predicted it in advance:
"at 10 A on a small target a shell can swallow most of the surface, making off-epitope
vacuous." At 10 A the shell contains roughly 57-64 of chain A's 275 residues, which is most
of the groove and both flanking helices, so a binder sitting anywhere on the peptide strip is
scored as fully on-epitope by construction.

A threshold cannot be pre-registered on a statistic with no spread. This sweep asks the prior
question: IS THERE A CUTOFF AT WHICH ITEM 1 DISCRIMINATES AT ALL? It reports, per cutoff, the
shell size and the spread of the resulting fraction across the ten designs.

This is a DIAGNOSTIC, not a selection. It does not choose a cutoff, does not rank designs and
does not gate. Choosing a cutoff on the spread it maximises would be fitting a free parameter
to this campaign's own ten designs, which is precisely the circularity UPGRADES.md section 5
rejects elsewhere. The output is evidence for the user's decision, and the decision is theirs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from contact_analysis import B2M_CHAIN, BINDER_CHAIN, HEAVY_CHAIN, PEPTIDE_CHAIN, assert_layout, load_chains
from tier0_targeting import FLAGS_PATH, contacted_residues, epitope_shell, load_flags

DEFAULT_CUTOFFS = (4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0)


def sweep_design(cif_path: Path, flags: dict, cutoffs) -> dict:
    chains = load_chains(cif_path)
    assert_layout(chains, cif_path)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", default=str(Path(__file__).parent / "artifacts"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    flags = load_flags(FLAGS_PATH)
    root = Path(args.artifacts)
    per_design: dict[str, dict] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        cif = d / f"{d.name}_predicted.cif"
        if cif.exists():
            per_design[d.name] = sweep_design(cif, flags, DEFAULT_CUTOFFS)

    summary: dict[str, dict] = {}
    for cut in DEFAULT_CUTOFFS:
        key = f"{cut:.1f}"
        vals = [v["by_cutoff"][key]["off_epitope_contact_fraction"] for v in per_design.values()]
        vals = [v for v in vals if v is not None]
        shells = [v["by_cutoff"][key]["shell_size_total"] for v in per_design.values()]
        summary[key] = {
            "off_epitope_min": round(min(vals), 5),
            "off_epitope_max": round(max(vals), 5),
            "off_epitope_median": round(statistics.median(vals), 5),
            "off_epitope_stdev": round(statistics.pstdev(vals), 5),
            "designs_at_zero": sum(1 for v in vals if v == 0.0),
            "shell_size_total_min": min(shells),
            "shell_size_total_max": max(shells),
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


if __name__ == "__main__":
    sys.exit(main())

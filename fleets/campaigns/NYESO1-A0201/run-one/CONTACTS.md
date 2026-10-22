# Run one — interface contact analysis (docking site, not specificity)

Local geometry over the mirrored run-one artifacts. No API calls, no spend. Produced by
`run-one/contact_analysis.py`; full numbers in `run-one/contact_analysis_results.json`.

## The question this answers, and the one it does not

`FLEET.toml [run_one] required_caveat` says nothing in run one can distinguish a binder that
engages the peptide from one that engages the invariant HLA framework. That caveat stands as
written for **specificity**, and is not weakened here. What it understates is narrower: the
mirrored coordinates do fix *where each binder sits*, and docking site is a geometric fact
available locally. This file settles docking site only. Specificity — whether a binder
discriminates `SLLMWITQC` from other peptides in the same groove — needs counter-screening
against decoy-loaded pMHC and remains entirely untested, exactly as the caveat says.

## Why raw counts and ipSAE could not answer it

The layer-2 result was that A|D ipSAE exceeded C|D for all ten designs, which reads as
framework engagement. But ipSAE is not normalised for interface size, and neither are raw
contact counts: a 9-residue peptide is out-measured by a 275-residue heavy chain by
construction. Both are the wrong instrument.

Two measures here are immune to that asymmetry:

1. **Per-position peptide contacts.** Whether the solvent-exposed, TCR-facing P4-P8 strip is
   engaged *at all* does not depend on chain size. Zero P4-P8 contact is framework-directed
   no matter how good `iptm` looks; broad P4-P8 engagement is a peptide readout even when
   chain A out-counts the peptide three to one.
2. **Fraction of available surface buried.** Of the surface each chain actually exposes in the
   assembled pMHC, how much does the binder cover. This normalises by what is there to grip.

## Result

All ten designs bury **56-82% of the peptide's available exposed surface** and only
**1.3-5.5% of the heavy chain's**. Every design contacts the TCR-facing P4-P8 strip; none
contacts the buried P2/P9 anchors, the alpha-3 Ig domain, or beta-2-microglobulin at all.
Chain A contact is **100% groove-proximal** (alpha-1 helix, alpha-2 helix, minor groove
floor) in all ten. The dominant contact in every design is **P5 (Trp5)**, the prominent
solvent-exposed residue of `SLLMWITQC`.

That is the canonical TCR-like footprint: straddling both groove-flanking helices for
footing while reading the central peptide bulge. The ipSAE ordering was a size artefact.

### How much of that is our own specification returned to us

Corrected 2026-10-22 per `UPGRADES.md` section 3. The peptide-directed finding must be read
with its circularity stated: `run-one/request-legacy-submitted.json` names **all nine**
peptide residues in `epitope_residues`, so the model bound where it was told to bind. The
footprint above is therefore substantially our own specification handed back to us, and is
**not** independent evidence of selectivity.

Two signals in this run were genuinely unconstrained and do carry information:

- **Zero contacts to the buried P2/P9 anchors.** Not specified by us; this is real geometry,
  and it is reproduced independently by `tier0_targeting.py` (item 3 = 0 for all ten).
- **Heavy-chain surface use of 1.3-5.5% only**, with `non_binding_residues` barred from the
  request body. Unconstrained, and the single most encouraging number here.

The honest summary: we told it where to bind and it bound there; *how* it bound there was its
own work. No measurement in this file has been changed or removed - only the interpretation
around it.

| design | iptm | D-pLDDT | A | B | C | pep frac (4.0/5.0 A) | % C buried | % A buried | P4-P8 | anchors | alpha3 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pres_KvvXtVa6yakB17EmB1Ge | 0.9825 | 82.02 | 66 | 0 | 69 | 0.511 / 0.486 | 77.9% | 4.0% | 64 | 0 | 0 | peptide-directed |
| pres_Bw8vknhmXJUg72L6CGAw | 0.9627 | 95.35 | 51 | 0 | 27 | 0.346 / 0.329 | 58.8% | 4.3% | 27 | 0 | 0 | peptide-directed |
| pres_rIVnI2qWY81pul3zHRrN | 0.9356 | 71.80 | 77 | 0 | 41 | 0.347 / 0.374 | 62.4% | 3.6% | 41 | 0 | 0 | peptide-directed |
| pres_JA4idjMYaE8EsQKrcb6K | 0.9249 | 77.82 | 59 | 0 | 50 | 0.459 / 0.383 | 66.8% | 3.5% | 50 | 0 | 0 | peptide-directed |
| pres_B8eqLRLyLSgzkVbLyC7C | 0.9033 | 76.23 | 52 | 0 | 54 | 0.509 / 0.487 | 75.6% | 4.2% | 53 | 0 | 0 | peptide-directed |
| pres_G3ZfGGLFJXddOc0vhQwO | 0.8732 | 72.43 | 72 | 0 | 46 | 0.390 / 0.356 | 81.5% | 5.5% | 44 | 0 | 0 | mixed (peptide-marginal) |
| pres_2SOqXG5xbTO4FD4yB5so | 0.8472 | 86.02 | 57 | 0 | 60 | 0.513 / 0.477 | 71.4% | 3.9% | 60 | 0 | 0 | peptide-directed |
| pres_lppWP1t4ozGyw5s4gq3P | 0.8388 | 86.53 | 51 | 0 | 52 | 0.505 / 0.505 | 76.8% | 3.4% | 52 | 0 | 0 | peptide-directed |
| pres_PfYJkQdsLag9x1R5Pt6L | 0.7876 | 90.82 | 49 | 0 | 52 | 0.515 / 0.483 | 56.5% | 2.8% | 52 | 0 | 0 | peptide-directed |
| pres_xpto8wJvfrJQhLVH4Mvz | 0.5105 | 82.26 | 6 | 0 | 56 | 0.903 / 0.829 | 60.4% | 1.3% | 56 | 0 | 0 | peptide-directed |

A/B/C are heavy-atom contact pairs to chains A, B, C at 4.0 A. `P4-P8` is heavy-atom contacts
to the TCR-facing strip; `anchors` is P2+P9.

Per-position P1-P9 contacts at 4.0 A, and contacted chain A regions:

| design | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | chain A regions |
|---|---|---|---|---|---|---|---|---|---|---|
| pres_KvvXtVa6yakB17EmB1Ge | 0 | 0 | 5 | 10 | 23 | 7 | 11 | 13 | 0 | a1 30, a2 36 |
| pres_Bw8vknhmXJUg72L6CGAw | 0 | 0 | 0 | 7 | 6 | 12 | 0 | 2 | 0 | a1 41, a2 3, floor 7 |
| pres_rIVnI2qWY81pul3zHRrN | 0 | 0 | 0 | 15 | 14 | 4 | 7 | 1 | 0 | a1 10, a2 67 |
| pres_JA4idjMYaE8EsQKrcb6K | 0 | 0 | 0 | 9 | 16 | 9 | 1 | 15 | 0 | a1 24, a2 35 |
| pres_B8eqLRLyLSgzkVbLyC7C | 0 | 0 | 1 | 6 | 19 | 3 | 8 | 17 | 0 | a1 27, a2 25 |
| pres_G3ZfGGLFJXddOc0vhQwO | 0 | 0 | 2 | 17 | 17 | 0 | 0 | 10 | 0 | a1 45, a2 27 |
| pres_2SOqXG5xbTO4FD4yB5so | 0 | 0 | 0 | 4 | 28 | 7 | 8 | 13 | 0 | a1 46, a2 10, floor 1 |
| pres_lppWP1t4ozGyw5s4gq3P | 0 | 0 | 0 | 6 | 32 | 0 | 3 | 11 | 0 | a1 34, a2 17 |
| pres_PfYJkQdsLag9x1R5Pt6L | 0 | 0 | 0 | 4 | 34 | 3 | 6 | 5 | 0 | a1 42, a2 6, floor 1 |
| pres_xpto8wJvfrJQhLVH4Mvz | 0 | 0 | 0 | 1 | 41 | 3 | 2 | 9 | 0 | a1 5, a2 1 |

## Two designs that deserve a second look

`pres_G3ZfGGLFJXddOc0vhQwO` is the one design called **mixed**, and only on breadth: it
engages P4, P5 and P8 but makes zero contact to P6 and P7, so three of five TCR-facing
positions rather than four. It buries the most peptide surface of any design (81.5%), so this
is a narrower grip, not a weaker one. The call is conservative by design.

`pres_xpto8wJvfrJQhLVH4Mvz` is the opposite outlier and should be treated with suspicion
rather than enthusiasm. It has almost no framework footing (6 contacts to chain A, 1.3% of
chain A surface, closest approach 3.44 A) and a peptide contact fraction of 0.90. A binder
perched on a 9-residue peptide with essentially no MHC contact is unlikely to be a real
binding mode, and its `iptm` of 0.5105 is the lowest in the set, below the 0.60 plausibility
threshold. The geometry and the confidence agree that this one is doubtful.

## Proof versus inference

**Proof** (measured from the mirrored coordinates, reproducible): all contact counts,
per-position and per-region breakdowns, contact fractions, buried areas and buried fractions
in the table and in `contact_analysis_results.json`.

**Inference** (judgement on top of those numbers): that this footprint constitutes
"peptide-directed" engagement, the thresholds separating peptide-directed from mixed, and the
reading of `pres_xpto8wJvfrJQhLVH4Mvz` as a doubtful pose. The classification thresholds are
stated in `classify()` and are **not calibrated** on pMHC-binder complexes; they are a
reasoned structural rule, not a validated classifier.

## What this does not establish

- **Nothing about specificity.** Binding the peptide-plus-helices surface is necessary for a
  peptide-directed binder but does not show the binder would *reject* a different peptide in
  the same groove. A binder can read P5 and still tolerate substitutions elsewhere. The
  specificity margin remains uncomputed and is a run-two endpoint.
- **The MAGE-A3 a3a / titin risk is untouched.** That failure was cross-reactivity with a
  different peptide presented by the same HLA, which this analysis cannot see by construction,
  since only the cognate complex was modelled. A peptide-directed footprint lowers the prior
  on the crudest framework-binding failure; it is not evidence against cross-reactivity.
- **Predicted, not experimental geometry.** Every number inherits Boltz's modelling error.
  Contact counts are sensitive to side-chain placement, which is the least reliable part of a
  predicted structure.
- **Non-gating.** These descriptors are recorded, not gates. Gating descriptors remain `iptm`
  and `plddt` only.

## Companion: Tier 0 targeting metrics

The four `UPGRADES.md` section 4 Tier 0 quantities are computed on these same coordinates, using
BindCraft2's G7 definitions rather than this file's campaign-specific rule: off-epitope contact
fraction, coldspot contact fraction, buried-anchor contact count and invariant-surface fraction.
Code and artifact paths are indexed in `UPGRADES.md` section 8, not repeated here. What those
measurements showed, and the proposals they raise, are in `../REFINEMENTS.md`.

Those metrics are **RECORDED-NON-GATING**. `UPGRADES.md` marks items 1-3 as *proposed* gates
needing the user's decision, and section 7 records that no calibrated threshold exists for any
of them. They change nothing in `FLEET.toml`.

## Environment and parameters

- Contacts and regions: `gemmi` 0.7.5, `numpy`, heavy atoms only (hydrogens excluded),
  inter-chain distance cutoffs **4.0 A primary, 5.0 A sensitivity**. Verdicts use 4.0 A.
- Run in two environments with **bit-identical** contact results: local `python3` 3.13.5 venv
  with gemmi 0.7.5, and the pinned image
  `ghcr.io/wetware-hq/bindi-fleet-env@sha256:7e8762ae...` under podman 5.4.2 (gemmi 0.7.5,
  numpy 2.4.6, Python 3.13.16).
- Buried surface area: `biotite` 2.0.0 Shrake-Rupley (`vdw_radii="Single"`, 200 test points),
  **local venv only** — biotite is not in the pinned image. `freesasa` was not usable: its
  wheel fails to build on Python 3.13 on this box. No BSA proxy was substituted.
- Chain layout asserted against every CIF before scoring: A 275 / B 99 / C 9 / D 73 with
  chain C sequence `SLLMWITQC`. This closes the open item that `BINDER_CHAIN = "D"` came from
  a comment rather than an artifact — it is now verified against all ten structures.

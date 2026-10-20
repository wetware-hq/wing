# non_binding_residues panels for campaign one (NY-ESO-1 / HLA-A*02:01)
Date 2026-10-20. NOT SUBMITTED. Built by BIO Scientist, pending BIO Physician residue-level sign-off.

## Numbering
Chain A value begins GSHSMRYFFTSVSRPGRGEPRFIAVGYVDDTQFVRF..., which is mature
HLA-A*02:01 heavy chain from Gly1. There is NO expression tag. Therefore:
    0-based index = mature author number - 1       (exact, no offset guesswork)
Chain A length 275 = author 1..275. Chain B = B2M, 99 aa. Chain C = SLLMWITQC, 9 aa.

## Verified structural facts (URLs fetched 2026-10-20)
- Domain boundaries alpha1 = 1-90, alpha2 = 91-182, alpha3 = 183-274 (mature numbering).
  IMGT domain lengths 90/92/92: https://www.imgt.org/IMGTrepertoireMH/2D-3Dstruct/SLlength/human/Hu_MHCtab1.html
  Also stated in https://doi.org/10.1007/s11434-014-0211-z (alpha1 1-90, alpha2 91-182).
- alpha3 is the Ig-like, membrane-proximal, CD8-binding domain; B2M is likewise
  membrane-proximal. Neither is part of a TCR or TCR-mimic footprint.
- A6 TCR / Tax-HLA-A2 contacts 15 HLA-A2 residues: SIX on the alpha1 helix
  (E58, R65, K66, K68, A69, Q72) and NINE on alpha2.
  https://rupress.org/jem/article/193/5/551/25976/
- "Restriction triad" R65, A69, Q155, plus Q72, V76, E154, A158 as frequent contacts.
  https://doi.org/10.4049/jimmunol.169.6.3146 and https://pmc.ncbi.nlm.nih.gov/articles/PMC5701626/
- JUDGEMENT, not fact: helix spans taken as alpha1 57-84 and alpha2 138-180 (author).
  These bracket every contact residue listed above. Not independently verified residue
  by residue against a crystal structure; treat the exact endpoints as approximate.

## The three panels (chain B = all 99 residues marked in every panel)
| Panel        | chain A marked (0-based)                     | marked | A left free | Triad R65/A69/Q155 marked? |
|--------------|----------------------------------------------|--------|-------------|----------------------------|
| conservative | 180-274                                      | 95     | 180         | no                         |
| targeted     | 180-274, 56-61, 76-83, 137-148, 166-179      | 135    | 140         | no                         |
| aggressive   | 180-274, 56-83, 137-179                      | 166    | 109         | yes                        |

conservative = alpha3 + B2M only. Marks off what should never be in any interface.
  Leaves the whole groove and both helices available. Lowest risk of making the design
  problem unsolvable; weakest steer away from conserved surface.
targeted = also marks the helix segments DISTAL to the peptide centre, leaving the
  central restriction-triad region contactable. Keeps the published de novo binding
  mode reachable while discouraging a sprawling framework footprint. My recommendation.
aggressive = marks both helices entirely, including R65/A69/Q155. The binder is pushed
  onto the 9-residue peptide and essentially nothing else.
  HONEST COST: a ~9-residue epitope is a very small interface for a 60-100 aa binder.
  This may be geometrically unsatisfiable, or yield designs that cannot express or fold.
  Published de novo pMHC binders DO contact helix. Treat as an experiment, not a default.

## Note on the earlier probe file
/workspace/wetware/binder-design/v2/pmhc/probe-nonbind.json already used chain A 180-274
and chain B 0-98. The conservative panel reproduces that choice exactly, deliberately.
Strict IMGT alpha3 is author 183-274 (0-based 182-273); 180-274 over-marks by three
residues at the alpha2/alpha3 junction. That over-marking is in the safe direction and
is retained for continuity with the probe.

## Not verified
- Whether the hosted BoltzGen honours non_binding_residues at all (support question sent
  2026-10-20; BoltzGen v0.3.2 fixed 'binding' being dropped when combined with 'not_binding').
- Whether any of the three panels changes cost. estimate-cost rejects the type:"binder" body.
- None of the three has been submitted. Nothing spent.

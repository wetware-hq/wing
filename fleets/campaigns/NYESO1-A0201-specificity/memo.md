# Reproducibility of the specificity margin in the NY-ESO-1/HLA-A*02:01 binder campaign

**Date:** 24 October 2026

## Abstract

**Background.** Candidate selection in this campaign rests on the specificity margin, a quantity derived from structure prediction of each designed binder against its cognate peptide-HLA complex and against a panel of ten single- and multi-residue decoy peptides. Candidates are promoted only above a prespecified margin threshold of 0.15. The threshold has been applied to a single prediction per design-peptide pair, and the stability of that prediction had not been assessed.

**Methods.** All 100 design-decoy structure predictions were regenerated and rescored with inputs and analysis code held identical to the archived run: the same ten binder sequences, the same decoy panel, the same interface confidence metrics and the same scoring pipeline. The archived and live panels were then compared design by design, for the specificity margin, for the sequence-derived developability liability verdicts and for the gating outcome.

**Results.** None of the 100 predictions reproduced; every per-prediction metrics record differed from its archived counterpart. The resulting specificity margins differed with a mean absolute difference of 0.0637, a maximum of 0.1174 and a standard deviation of 0.0725, against a prespecified threshold of 0.15. The leading candidate moved from 0.085826 to 0.163938 and so crossed the threshold, changing the campaign result from 0 of 10 candidates above threshold to 1 of 10. Sequence-derived liability verdicts were unchanged in all ten candidates. No candidate was promoted in either run, because independent liability and unpinned-gate blocks held. Predictions were generated without a recorded random seed, and the declared content address names a seed that is never set, so the published manifest hash was identical across the two divergent runs.

**Conclusions.** Run-to-run variation in the specificity margin approaches the magnitude of the decision threshold itself. A single unseeded prediction therefore cannot support a fixed-threshold gate at this effect size, and near-threshold ranking should be treated as indeterminate rather than as a result.

## The target

NY-ESO-1, the product of the CTAG1B gene, is a cancer-testis antigen. In the healthy adult its expression is confined to germ cells of the testis and to placenta. It is absent from normal somatic tissue, and it is re-expressed aberrantly in a range of tumours, among them synovial sarcoma, myxoid round-cell liposarcoma, melanoma and ovarian carcinoma. The germ cells that express it do not display class I major histocompatibility molecules, so in normal tissue the antigen is never presented to CD8 T cells. Two consequences follow, and both favour the target: tolerance to NY-ESO-1 is incomplete, so it remains immunogenic, and no normal somatic tissue presents it, so the expected risk of on-target off-tumour toxicity is low.

A binder cannot reach NY-ESO-1 itself. The protein is intracellular. What a cell displays on its surface is a short fragment of it, held in the peptide-binding groove of a class I molecule. In this campaign that fragment is the nine-residue peptide SLLMWITQC, residues 157 to 165, presented by HLA-A*02:01, one of the most common class I alleles in most populations. The object of the design is therefore the assembled complex of peptide, heavy chain and beta-2 microglobulin, not the antigen as a soluble protein. Every structure prediction reported below is a prediction of that complex, and the binder is required to engage it.

The surface such a binder sees is mostly allele, not antigen. The groove and its flanking helices are identical on every HLA-A*02:01 molecule the patient carries, and only the few outward-facing residues of the bound peptide distinguish one complex from another. A binder that derives its affinity from the groove will bind HLA-A*02:01 presenting anything. Specificity in this campaign is defined against precisely that failure. Each candidate is scored against its cognate complex and against ten decoy complexes that carry the same allele and differ only in the peptide, with the substitutions concentrated at positions 4 to 8, the residues that face outward. The specificity margin is the cognate score minus the best decoy score. It asks one question: does the binder discriminate the peptide, or only the groove?

The hazard is not hypothetical. An affinity-enhanced T-cell receptor raised against another cancer-testis antigen, MAGE-A3, was found to recognise an unrelated peptide from the muscle protein titin presented by the same class I allele. The first two patients treated died of cardiogenic shock within days of infusion, and the preclinical specificity screens had not predicted it (Linette et al., Blood 2013; Cameron et al., Science Translational Medicine 2013). The panel used here probes discrimination within the cognate epitope only. A panel of unrelated self peptides presented by HLA-A*02:01 has been specified but not assembled, and remains an open decision. The margin reported below is a necessary screen, not evidence of clinical specificity.

## Figure

![Specificity margin for ten binder candidates in two runs with identical inputs, against the prespecified 0.15 threshold](memo_figure.png)

**Figure 1.** Specificity margin for each of the ten binder candidates (n = 10 designs, each scored against a panel of ten decoy peptides, 100 structure predictions per run) in two runs that used identical binder sequences, identical decoy panel and identical analysis code. Open circles denote the archived run, filled circles the live run, and the connecting rule the movement between them; the vertical line marks the prespecified threshold of 0.15, and the faint line marks zero. The two horizontal rules at the foot are drawn on the same scale as the data: the upper spans the full decision distance from 0 to the 0.15 threshold, the lower the largest observed run-to-run shift of 0.117352. The reader should take from the figure that the movement attributable to rerunning the prediction alone is of the same order as the distance the threshold is meant to discriminate, and that this is sufficient to carry the leading candidate, rIVnI2qWY81pul3zHRrN, from 0.085826 to 0.163938 and across the threshold.

## Open decisions

Three courses are available, and they are not mutually exclusive. The first is to pin and record a random seed for each prediction, which would make the declared content address and the manifest hash truthful; it would not make runs reproducible, and it would not make any single draw more trustworthy, since a seeded value remains one sample from the same distribution. Appendix 1 reports a direct test of this course. The second is to replicate each prediction and gate on a confidence interval rather than a point estimate, which addresses the dispersion directly but scales linearly in cost: three replicates of 100 predictions is approximately $15.00 at $0.05 per prediction, which exceeds the remaining approval cap, so a replicate design requires either a revised cap or a reduced panel. The third is to revisit whether a fixed threshold of 0.15 is defensible at all on a quantity whose run-to-run standard deviation is 0.0725, as against widening it into a band with an explicit indeterminate verdict or replacing it with a ranked comparison against the decoy panel that does not depend on an absolute cut.

## Appendix 1. Attribution of the variation to the random seed

**Question.** Whether the run-to-run dispersion reported above is attributable to sampling without a fixed random seed.

**Methods.** The leading candidate, rIVnI2qWY81pul3zHRrN, was studied, this being the design whose threshold crossing the dispersion decided. Its full ten-peptide decoy panel was predicted twice under an identical pinned random seed of 20261024 and identical sampler settings of 3 recycling steps, 200 sampling steps and a diffusion step scale of 1.638, giving 20 predictions. All other inputs were held as in the main comparison. Three controls establish that the pinned settings took effect rather than being ignored: the prediction service rejects unrecognised sampler options, every response returned the pinned settings as submitted, and the ten requests were identical between the two arms. Absent these controls, a negative result could not be distinguished from a seed that was never applied.

**Results.** Predictions were not identical under a pinned seed. Five of the ten structures reproduced exactly and five did not. The specificity margin was 0.150682 in the first arm and 0.150285 in the second, a difference of 0.000397, against 0.078112 between the two unseeded runs of the same design: approximately 197-fold narrower.

| Condition | Margin, run 1 | Margin, run 2 | Difference |
| --- | ---: | ---: | ---: |
| Pinned seed | 0.150682 | 0.150285 | 0.000397 |
| Unseeded | 0.085826 | 0.163938 | 0.078112 |

**The difference that remains is larger than the margin that is being read.** Both seeded arms clear the 0.15 threshold, by 0.000682 and 0.000285 respectively. The residual difference between them, 0.000397, exceeds the smaller of those two distances and is of the same order as the larger. A design that passes by less than the variation remaining after the seed is fixed has not been shown to pass.

Two further observations bear on interpretation. Neither seeded value reproduces either unseeded value; pinning the seed returned a third answer rather than one of the two already obtained. And the decoy peptide that set the margin differed between conditions, being decoy_p5_w_to_a when unseeded and decoy_p6a_p7a in both seeded arms. A design's measured specificity therefore depends in part on which decoy happens to score highest in the draw at hand.

**Limitation.** Two runs per condition demonstrate non-identity but cannot estimate a variance. The fold-differences above compare single observed spreads, not estimated variances, and should be read as indicative of magnitude only.

**Interpretation.** Pinning the seed is necessary and insufficient. It removes most of the dispersion without making any single prediction reproducible, and it does not render a threshold verdict trustworthy for a design lying this close to the line.

# Reproducibility of the specificity margin in the NY-ESO-1/HLA-A*02:01 binder campaign

**Date:** 24 October 2026

## Abstract

**Background.** Candidate selection in this campaign rests on the specificity margin, a quantity derived from structure prediction of each designed binder against its cognate peptide-HLA complex and against a panel of ten single- and multi-residue decoy peptides. Candidates are promoted only above a prespecified margin threshold of 0.15. The threshold has been applied to a single prediction per design-peptide pair, and the stability of that prediction had not been assessed.

**Methods.** All 100 design-decoy structure predictions were regenerated and rescored with inputs and analysis code held identical to the archived run: the same ten binder sequences, the same decoy panel, the same interface confidence metrics and the same scoring pipeline. The archived and live panels were then compared design by design, for the specificity margin, for the sequence-derived developability liability verdicts and for the gating outcome.

**Results.** None of the 100 predictions reproduced; every per-prediction metrics record differed from its archived counterpart. The resulting specificity margins differed with a mean absolute difference of 0.0637, a maximum of 0.1174 and a standard deviation of 0.0725, against a prespecified threshold of 0.15. The leading candidate moved from 0.085826 to 0.163938 and so crossed the threshold, changing the campaign result from 0 of 10 candidates above threshold to 1 of 10. Sequence-derived liability verdicts were unchanged in all ten candidates. No candidate was promoted in either run, because independent liability and unpinned-gate blocks held. Predictions were generated without a recorded random seed, and the declared content address names a seed that is never set, so the published manifest hash was identical across the two divergent runs.

**Conclusions.** Run-to-run variation in the specificity margin approaches the magnitude of the decision threshold itself. A single unseeded prediction therefore cannot support a fixed-threshold gate at this effect size, and near-threshold ranking should be treated as indeterminate rather than as a result.

## Figure

![Specificity margin for ten binder candidates in two runs with identical inputs, against the prespecified 0.15 threshold](memo_figure.png)

**Figure 1.** Specificity margin for each of the ten binder candidates (n = 10 designs, each scored against a panel of ten decoy peptides, 100 structure predictions per run) in two runs that used identical binder sequences, identical decoy panel and identical analysis code. Open circles denote the archived run, filled circles the live run, and the connecting rule the movement between them; the vertical line marks the prespecified threshold of 0.15, and the faint line marks zero. The two horizontal rules at the foot are drawn on the same scale as the data: the upper spans the full decision distance from 0 to the 0.15 threshold, the lower the largest observed run-to-run shift of 0.117352. The reader should take from the figure that the movement attributable to rerunning the prediction alone is of the same order as the distance the threshold is meant to discriminate, and that this is sufficient to carry the leading candidate, rIVnI2qWY81pul3zHRrN, from 0.085826 to 0.163938 and across the threshold.

## Open decisions

Three courses are available, and they are not mutually exclusive. The first is to pin and record a random seed for each prediction, which would make runs reproducible and would make the declared content address and the manifest hash truthful; it would not make any single draw more trustworthy, since a seeded value remains one sample from the same distribution, merely a repeatable one. The second is to replicate each prediction and gate on a confidence interval rather than a point estimate, which addresses the dispersion directly but scales linearly in cost: three replicates of 100 predictions is approximately $15.00 at $0.05 per prediction, which exceeds the remaining approval cap, so a replicate design requires either a revised cap or a reduced panel. The third is to revisit whether a fixed threshold of 0.15 is defensible at all on a quantity whose run-to-run standard deviation is 0.0725, as against widening it into a band with an explicit indeterminate verdict or replacing it with a ranked comparison against the decoy panel that does not depend on an absolute cut.

# CASE — NY-ESO-1 157-165 / HLA-A*02:01

**Target id:** `NYESO1-A0201` · **Case version:** 1.0 · **Date:** 2026-10-20
**Scope:** in vitro only. No in vivo work is planned or implied.
**Status:** nothing submitted, nothing spent.

> This file is the clinical half of the specification: the case, the target, and the
> mechanistic argument, written to be read by a clinician. The executable half — the
> agentic graph, the gates, the thresholds, the platform contract and the owners
> register — is `FLEET.toml` in this directory. Neither file duplicates the other.

---

## Clinical case

The demonstration indication, decided with BIO Physician, is **resected high-tumour-mutational-burden cutaneous melanoma treated in the minimal-residual-disease / adjuvant window**. The product class is **TCR-mimic antibodies and de novo minibinders** — agents that recognise a tumour antigen in the context of HLA rather than a surface protein.

The MRD framing is anchored to randomised and early-phase evidence that antigen-directed therapy acts in the post-resection window rather than in bulk disease: TG4050 in resected head and neck squamous cell carcinoma (0 of 16 relapses in the treated arm against 3 of 16 in the control arm) and the triple-negative breast cancer phase data assembled by BIO Physician. The clinical bet is that a defined antigen, targeted while disease burden is minimal, is where a binder of this class can plausibly matter.

## Target selection, and what it does and does not prove

On 2026-10-20 the campaign-one target was set to a **published, shared cancer-testis antigen**, not a patient-specific private neoantigen:

| Parameter | Value |
|---|---|
| Antigen | NY-ESO-1 (cancer-testis; shared, not private) |
| Epitope | residues 157-165 |
| Peptide | `SLLMWITQC` (9-mer) |
| Restricting allele | HLA-A*02:01 |
| Complex | 3-chain class I pMHC (heavy chain, beta-2-microglobulin, peptide) |

The reasons on the record: it validates the pipeline against a known answer; it skips the phase-0 mass-spectrometry confirmation gate a private neoantigen would require; it has documented off-target behaviour in the literature; and it is cheap. Patient-specific neoantigens are deferred to later campaigns.

**The honest limit.** A cancer-testis antigen is shared across many patients. Campaign one therefore proves that the pipeline works end to end against a known-answer target. **It does not demonstrate personalised medicine.** That requires a private-neoantigen campaign, which is explicitly deferred and not claimed here.

## Mechanism: why specificity, not affinity, is the product

A class I pMHC presents a 9-residue peptide in a groove formed by the alpha-1 and alpha-2 helices of the HLA heavy chain. In natural TCR–pMHC class I interfaces the peptide contributes only about **12-49%** of the buried surface area, mean roughly **29%** ([PMC7793522](https://pmc.ncbi.nlm.nih.gov/articles/PMC7793522/)). The remaining majority of the contact surface is invariant HLA framework — structure present on every nucleated cell in the body.

The clinical consequence is direct. A binder that engages mostly framework is not a *weak* agent, it is an *unsafe* one, because framework is ubiquitous and a framework-directed agent will engage healthy tissue. The reference failure is the MAGE-A3 affinity-enhanced TCR, which cross-reacted with titin and killed two patients by cardiogenic shock.

Cross-reactive clones are therefore treated as an **expected output** of any generative design method, to be screened out by construction — not as a tail risk to be hoped away. Everything downstream follows from this: the primary endpoint of the computational campaign is the **specificity margin**, the on-target rank minus the best-decoy rank for a given design. High affinity for framework is a failure, not a partial success.

## What the in-silico campaign is, in clinical terms

The campaign designs candidate binders against the real `SLLMWITQC`/HLA-A*02:01 complex and then re-folds the survivors against a panel of closely related decoy peptides on the *same* HLA. A design is only interesting if it ranks well on the real epitope **and** poorly on the decoys. The decoy panel for the reproduction is ten peptide mutants of `SLLMWITQC` (nine single or double mutants and one quadruple mutant); a clinically motivated panel of proteome near-neighbours and self-peptides is a planned extension and is owned by BIO Physician.

## What is reproduced, and what is not

The reproduction target is bioRxiv [10.1101/2024.11.27.624796](https://doi.org/10.1101/2024.11.27.624796), with companion method paper [10.1101/2024.11.28.625793](https://doi.org/10.1101/2024.11.28.625793). The published gates are defined on AlphaFold2 initial guess, a model this stack does not contain, and the Boltz interface-error quantity is not the same measurement. The stated position is that we reproduce the paper's **logic, not its numbers**, with thresholds recalibrated on campaign one. This is a live decision, recorded in `FLEET.toml`.

## Three things a reader should not be allowed to miss

1. **Campaign one proves the pipeline, not personalisation.** Shared antigen, by choice.
2. **Every quality threshold is transferred, not calibrated.** They come from a protein-protein interaction benchmark containing no pMHC complexes at all. Campaign one is itself the calibration experiment.
3. **There is no independent model confirming any design.** The architecture was cut to two layers, removing the orthogonal re-predictor. Anything the generator is *systematically* wrong about will pass undetected. The specificity margin is a differential under one model, so a shared bias cancels to first order — but a peptide-dependent bias does not cancel.

## Downstream hand-off (in vitro, owned by BIO Physician)

Surface plasmon resonance or bio-layer interferometry for affinity; counter-screening against the decoy and self-peptide panels for specificity; multimer staining and a Jurkat-NFAT reporter for functional engagement; optionally co-culture cytotoxicity; and developability assessment. Whether the reproduction bar includes co-culture cytotoxicity or stops at multimer plus Jurkat-NFAT is an open decision owned by BIO Physician.

## Governance

Nothing is submitted and no money is spent without Mathew's explicit approval. The approval and spend cap are not prose in this file — they are a node inside the execution graph in `FLEET.toml`, and the graph halts at zero cost if approval is withheld.

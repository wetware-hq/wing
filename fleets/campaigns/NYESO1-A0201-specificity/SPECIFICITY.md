# Specificity margin — NYESO1-A0201-specificity

**Campaign id:** `NYESO1-A0201-specificity` · **Parent:** `NYESO1-A0201` · **Date:** 2026-10-23  
**Primary endpoint:** `specificity_margin` (on-target rank − best-decoy rank)

## Definition

For each survivor binder (fixed chain D sequence from run-one), Boltz refolds the **same**
HLA-A*02:01 + β2m complex with:

1. The **cognate** peptide `SLLMWITQC` (on-target).
2. Each **decoy** peptide from the panel (OD-3; P4–P8-focused mutants).

Layer 2 scores every refold with the existing pure-CPU path (`layer2_orchestrator.py` in
`../NYESO1-A0201/run-one/`, `bindi` ipSAE + contact geometry + recorded Tier-0 / item-10).

Within one survivor, each peptide receives a **rank_average** over the descriptor stack declared
in `FLEET.toml`:

| Descriptor | Source (L2) | Direction |
|---|---|---|
| `complex_iplddt` | `metrics.json` | higher better |
| `shape_complementarity` | item-10 `complementarity_contact_fraction_delta` | higher better |
| `plddt` | chain D mean from ipSAE parse | higher better |
| `min_ipsae` | ipSAE pairs | higher better |
| `ipsae` | C\|D ipSAE | higher better |
| `iptm` | `metrics.json` | higher better |
| `pae_interaction` | `min_interaction_pae` in `metrics.json` | **lower** better |

Peptides are ordinally ranked by ascending `rank_average` (rank **1** = best).

```
specificity_margin = on_target_rank − best_decoy_rank
```

**Interpretation (rank 1 = best):** negative or zero margin means the cognate ranks at least as
well as the strongest decoy — the in-silico **draft** pass rule for hand-off is
`specificity_margin <= 0`. Positive margin means a decoy outranks the cognate (specificity failure
under this stack).

`iptm` and binder `plddt` alone are **not** the ranking key; they enter only as terms in
`rank_average`.

## Artifact layout (post-L1B)

```
artifacts/
  <design_id>/                    # e.g. pres_KvvXtVa6yakB17EmB1Ge
    cognate_SLLMWITQC/
      <job>_predicted.cif
      metrics.json
      pae.npz
    decoy_01_.../
      ...
```

Run-one cognate-only mirrors remain valid for calibration:

```
../NYESO1-A0201/run-one/artifacts/<design_id>/
```

## Execution graph (this campaign)

See `FLEET.toml`: **CFG → APPR → L1B → ART → L2 → MARGIN → PANEL**. L1A is skipped; survivors
are listed in `survivor_panel.yaml`.

## Pass / hand-off to in vitro (BIO Physician)

| Stage | Criterion | Owner |
|---|---|---|
| In silico (this campaign) | Margin computed with full decoy panel; top designs by margin (not iptm) | BIO Scientist |
| Draft in-silico bar | `specificity_margin <= 0` + contact geometry recorded on cognate refold | BIO Scientist |
| In vitro | SPR/BLI, decoy/self counter-screen, multimer + Jurkat-NFAT (OD-5) | BIO Physician |

Thresholds remain **transferred** until OD-1 recalibration on this run completes.

## Commands

```bash
# Ranked panel stub (run-one cognate only; margin incomplete until OD-3 + L1B)
python3 fleets/campaigns/NYESO1-A0201-specificity/specificity_orchestrator.py

# Full L2 rescore per peptide directory tree
python3 fleets/campaigns/NYESO1-A0201-specificity/specificity_orchestrator.py --score

# L1B request manifest (after decoy_panel.yaml sequences are filled)
python3 fleets/campaigns/NYESO1-A0201-specificity/specificity_orchestrator.py \
  --write-l1b-manifest fleets/campaigns/NYESO1-A0201-specificity/artifacts/l1b_manifest.json
```

## Open decisions (must stay visible)

| Id | Question | Default |
|---|---|---|
| OD-1 | Recalibrate thresholds on this run vs keep transferred | Recalibrate (Mathew) |
| OD-2 | Negative-design panel | **targeted** |
| OD-3 | Ten decoy sequences | BIO Physician |
| OD-4 | Self / proteome-near-neighbour panel | BIO Physician |

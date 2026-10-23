# Specificity margin — NYESO1-A0201-specificity

**Campaign id:** `NYESO1-A0201-specificity`  
**Primary endpoint:** `specificity_margin` (ranking key: `margin_first`)  
**Survivor source:** `../NYESO1-A0201/run-one/artifacts/` (run-one positive control; L1B decoy refolds pending)

Clinical framing lives in `../NYESO1-A0201/CASE.md`. Executable graph and spend cap live in `FLEET.toml` in this directory.

---

## Margin formula

Layer 2 computes a **peptide–binder ipSAE** score for each complex (chain C|D minimum ipSAE from the bindi worker, same path as run-one).

For each survivor design *d*:

1. **On-target score** — ipSAE on the cognate peptide `SLLMWITQC` complex (artifact under `pres_<id>/` or mirrored decoy tree).
2. **Decoy scores** — same metric on each L1B refold with a decoy peptide from `decoy_panel.yaml` (artifact layout below).
3. **Score margin (primary, gating):**
   ```text
   specificity_margin = on_target_ipsae_cd − max(decoy_ipsae_cd)
   ```
   Higher is more selective under a single model. Hard gate: `specificity_margin >= 0.15` (pre-registered in `FLEET.toml`; not calibrated on pMHC).

4. **Rank margin (transport, secondary field):** complexes for design *d* are sorted by descending ipSAE (rank 1 = strongest). Then:
   ```text
   rank_margin = best_decoy_rank − on_target_rank
   ```
   Positive rank margin means the cognate beats the best decoy in rank space. The fleet manifest text uses “on-target rank − best-decoy rank”; the JSON panel stores both score margin (primary) and integer ranks for audit.

Until L1B decoy artifacts exist, `specificity_margin` is `null` with `margin_status: pending_l1b`.

---

## Liability filters (pure CPU, sequence-first)

Applied to the **designed binder chain D** sequence parsed from the cognate CIF. No GPU.

| Filter | Mode | Rule |
|--------|------|------|
| Motif scan | hard | Regex motifs: `NG`, `NS`, `NT`, `NH`, `DG`, `DS`, `DT`, `N[^P][ST]` |
| Unpaired Cys | hard | Any cysteine in the binder sequence fails (`unpaired_cys: hard_fail`) |
| Exposed oxidation | hard | Count of `{M, W}` in sequence ≥ `threshold` (1) — sequence proxy until solvent exposure is wired |
| SAP patch | soft | Placeholder: no SAP executable in fleet env; `sap_patch` recorded as `skipped_no_sap` and does not hard-fail |

**Developability score** (secondary rank key): starts at `1.0`, subtract `0.15` per matched liability motif, subtract `0.1` if soft SAP would fire (when implemented). Hard fails set `liability_filters.pass = false`.

`allow: none` — no motif allow-list.

---

## Other gates

| Gate | Type | Rule |
|------|------|------|
| `buried_anchor_contacts` | hard | Tier 0 `item_3_buried_anchor_contact_count == 0` |
| `iptm` | soft | ≥ 0.60 |
| `chain_D_plddt` | soft | mean pLDDT on chain D ≥ 80 |

---

## Ranking hierarchy

1. `specificity_margin` (desc; nulls last)  
2. `developability_score` (desc)  
3. `iptm` (desc)

Diversity (`DIV`) remains downstream of Layer 2 in the graph; panel JSON is pre-DIV ranked list.

Hand-off: top ≤ 3 designs by primary key → BIO Physician (`handoff_top_n = 3`).

---

## Artifact layout for decoy refolds

```
run-one/artifacts/
  pres_<design_id>/                 # cognate (from run-one or L1A/L1B)
  decoy_refolds/
    <design_id>/
      <decoy_id>/
        <job_or_run_id>_predicted.cif
        metrics.json
        pae.npz
```

Provenance on every panel row: job id, relative artifact paths, `layer2_core.LAYER2_PINS` (image digest + bindi wheel SHA), API contract version from `FLEET.toml`.

---

## Open decisions (not silently resolved)

| Id | Owner | Question |
|----|-------|----------|
| OD-1 | Mathew | Boltz-native thresholds vs reinstate AF2 initial guess |
| OD-2 | Mathew + BIO Physician | Negative-design panel (`targeted` recommended) |
| OD-3 | BIO Physician | Ten exact decoy sequences (proposals in `decoy_panel.yaml` until signed) |
| OD-4 | BIO Physician | Self-peptide / proteome-near-neighbour panel |
| OD-1 (infra) | BIO Scientist + Engineer | RO-Crate / Nextflow superset (OD-8 in parent fleet) |

---

## Validation checklist

- Token alignment: bindi worker raises `TokenAlignmentError` on mismatch (unchanged).
- Outputs: JSON with `sort_keys=True` for hashing.
- Layer 2: pure CPU, single-thread BLAS in pinned ghcr image; no GPU spend.
- APPR: `$14.50` spend cap on approve path.
- Panel: ≤ 3 hand-off rows when margin is computable.

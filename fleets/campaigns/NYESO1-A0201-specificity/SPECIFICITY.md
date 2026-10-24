# Specificity margin — NYESO1-A0201-specificity

**Campaign id:** `NYESO1-A0201-specificity` · **Parent:** `NYESO1-A0201` · **Date:** 2026-10-23  
**Primary endpoint (manifest):** `specificity_margin` · **Ranking:** `margin_first`

Two computation paths exist in this repository after merging main (#12) and the A2A Layer 2
extension (#13). **Path A is the primary hard gate** (physician sign-off 2026-10-23). Path B is
computed and recorded in parallel when using `specificity_orchestrator.py` but does not gate L1B
or hand-off.

> **Multi-objective upgrade (2026-10-24):** terminal selection is now a four-axis Pareto judge
> (potency / specificity / developability / immunogenicity-safety) with scalar compositing forbidden,
> a staged selection funnel, calibration anchors, judge blinding, and first-class rejection tracking.
> See **`SCORING.md`** and `FLEET.toml` `[scoring]`/`[judge]`/`[[stages]]`/`[rejections]`. Path A below
> remains the specificity hard gate within that judge.

---

## Path A — ipSAE score margin (Layer 2 `--specificity-campaign`) **primary**

Implemented in `../NYESO1-A0201/run-one/specificity_scoring.py` and
`layer2_orchestrator.py --specificity-campaign`.

For each survivor design *d*:

1. **On-target score** — chain C|D min ipSAE on the cognate complex (run-one `pres_*` or L1B cognate refold).
2. **Decoy scores** — same metric on each decoy under `artifacts/decoy_refolds/<design_id>/<decoy_id>/`.
3. **Score margin (hard gate in `FLEET.toml`):**
   ```text
   specificity_margin = on_target_ipsae_cd − max(decoy_ipsae_cd)
   ```
   Hard gate: `specificity_margin >= 0.15` (provisional; recalibrate on this run — OD-1).

4. **Rank audit fields:** peptides sorted by descending ipSAE; `rank_margin = best_decoy_rank − on_target_rank`.

**Also on this path:** pure-CPU **liability filters** (motif scan, Cys, M/W proxy, SAP placeholder),
**developability_score** (secondary rank key), **buried_anchor_contacts == 0**, soft iptm / chain-D pLDDT.

Until L1B decoy artifacts exist, margin is `null` with `margin_status: pending_l1b`.

### Path A artifact layout

```
../NYESO1-A0201/run-one/artifacts/
  pres_<design_id>/                 # cognate (run-one)
  decoy_refolds/
    <design_id>/
      <decoy_id>/
        *_predicted.cif
        metrics.json
        pae.npz
```

### Path A command

```bash
cd ../NYESO1-A0201/run-one
python3 layer2_orchestrator.py --specificity-campaign \
  --decoy-panel ../../NYESO1-A0201-specificity/decoy_panel.yaml
```

Outputs: `artifacts/panel.json` (ranked PANEL + top ≤3 hand-off).

---

## Path B — rank_average rank margin (#12 stub, audit only)

Implemented in `specificity_margin.py` and `specificity_orchestrator.py`.

Boltz refolds each survivor against cognate + decoys (see `FLEET.toml` L1B / `l1b_request_builder.py`).
Layer 2 scores each peptide; descriptors are combined with **rank_average** over the stack in
`FLEET.toml` `[descriptors]`. Within one survivor:

```text
specificity_margin = on_target_rank − best_decoy_rank
```

(rank **1** = best = lowest rank_average). **Not used as the campaign hard gate** (Path A ≥ 0.15 applies).

### Path B artifact layout (post-L1B)

Path B reads the **same tree as Path A** — the cognate refold sits directly in the
per-design dir, and the decoy refolds are written by
`l1b_runner.py:mirror_prediction_to_decoy_dir` under `decoy_refolds/`:

```
../NYESO1-A0201/run-one/artifacts/
  pres_<design_id>/                 # cognate; *_predicted.cif sits directly here
    pres_<design_id>_predicted.cif
    metrics.json
    pae.npz
  decoy_refolds/
    pres_<design_id>/
      <decoy_id>/                   # one dir per decoy peptide
        <decoy_id>_predicted.cif
        metrics.json
        pae.npz
```

`collect_peptide_artifact_dirs()` collects **both** trees and keys the cognate
`cognate_SLLMWITQC`. It also still accepts the legacy `artifacts/<design_id>/<peptide_id>/`
subtree from the #12 stub. Earlier revisions of this section documented only that legacy
shape, which is not what the L1B runner writes.

### Path B commands

```bash
python3 fleets/campaigns/NYESO1-A0201-specificity/specificity_orchestrator.py
python3 fleets/campaigns/NYESO1-A0201-specificity/specificity_orchestrator.py --score
python3 fleets/campaigns/NYESO1-A0201-specificity/specificity_orchestrator.py \
  --write-l1b-manifest fleets/campaigns/NYESO1-A0201-specificity/artifacts/l1b_manifest.json
```

---

## Execution graph

`FLEET.toml`: **CFG → APPR → L1B → ART → L2 → MARGIN → PANEL**. L1A is skipped; survivors are
in `survivor_panel.yaml`.

---

## Decoy panel

`decoy_panel.yaml` — ten signed decoys (7 single / 2 double / 1 triple on P4–P8).
`panel_ready_for_l1b: true` (BIO Physician 2026-10-23). `self_peptides` empty (OD-4 deferred).

---

## Open decisions

| Id | Question | Status |
|---|---|---|
| OD-1 | Recalibrate thresholds on this run vs transferred | Open — provisional gates in force |
| OD-2 | Negative-design panel | **Resolved: targeted** |
| OD-3 | Ten decoy sequences | **Resolved — signed panel** |
| OD-4 | Self / proteome panel | **Deferred** |

---

## Path A vs Path B (reference)

| Topic | Path A (primary) | Path B (parallel / audit) |
|---|---|---|
| Margin definition | ipSAE C|D score difference | Ordinal rank from rank_average stack |
| Pass direction | Higher margin better; gate **≥ 0.15** | Rank margin; draft pass **≤ 0** |
| L1B API | Decoy refolds (layout above); parent **LEGACY design** unchanged | **`/protein/predict`** via `l1b_request_builder.py` |
| Hand-off ranking | margin → developability → iptm | rank margin on descriptor stack |

---

## Validation checklist

- Token alignment: bindi `TokenAlignmentError` unchanged.
- Deterministic JSON: `sort_keys=True` on panel outputs.
- Layer 2: pure CPU; no GPU in scoring path.
- APPR: `$14.50` spend cap.
- Hand-off: ≤ 3 designs when margin is computable on Path A.

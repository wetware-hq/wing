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

> **Predictions are stochastic and unseeded (2026-10-24).** Every margin on this page is computed
> from a single unseeded draw of a structure prediction. Re-running the identical inputs returns
> different structures and therefore different margins: measured over n=10 designs across two runs
> with identical sequences, decoy panel and code, `specificity_margin` moved by a mean absolute
> 0.0637 (max 0.1174, SD 0.0725) against the 0.15 hard gate, and the lead design crossed the gate
> on the second run. Read any single margin, and any ranking of margins near the gate, as one draw
> rather than a property of the design. See `FLEET.toml` `[stochasticity]`, OD-5, and `memo.md`.

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
   Prior hard gate `specificity_margin >= 0.15` **retired** as objective by OD-11 (demoted sign-test mean > 0 over N=10; geometry is primary). Anchors + liability remain hard.

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


## Finding 0 — Path A measurement protocol (OD-9)

U-6 established that the two legs of `specificity_margin` were never produced by
the same pipeline: on-target from design job (`prot_des_*`, design-metrics schema),
decoys from prediction (`sab_pred_*`, prediction-metrics schema). Schemas are
disjoint beyond six shared confidence fields. On equal footing the lead design
gives **0/20** combinations ≥ 0.15 (means −0.113344 and −0.035232). Recorded
positive margins that mixed the pipelines are artefacts.

**OD-9 (decided):** both legs of Path A come from the structure-and-binding
prediction endpoint via `l1b_request_builder.build_structure_and_binding_payload`.
Design-job on-target scores are not a Path A margin input. Cost in evidence:
every prior mixed-pipeline "pass" (including the lead's recorded 0.163938) is
non-gating under this protocol. The 0.15 threshold was unchanged by OD-9;
OD-11 later retired it as the campaign objective (see below).

Implementation status: protocol decided; fail-loud guard not yet wired into
`layer2_orchestrator.py` / `specificity_scoring.py` (OD-10 Arm 0).

## Burial fraction is not specificity margin

`peptide_burial_fraction` is the peptide share of binder buried surface on the
cognate pose. `specificity_margin` is cognate ipSAE_CD − max(decoy ipSAE_CD).
They answer different questions and are **unlinked** under OD-11. Geometric
ceiling (`/workspace/burial_ceiling/REPORT.md`): peptide is 2.3% of target SASA;
corrected-best already covers 0.723 of the peptide face; projecting to full
peptide coverage at fixed HLA footprint yields burial only **0.4666**. Raising
peptide grip alone cannot clear ~0.47 burial.

U-6 equal-footing data (n=10 draws, one design): Spearman
ρ(burial, cognate_ipsae_cd) = **−0.5276**. Under OD-11 this is a
disagreement-series seed written toward `artifacts/disagreements.jsonl`, **not**
evidence against OD-8 targeting and not a reason to relax peptide proximity.

## Geometric objective (OD-11) and campaign (OD-10 reconciled)

**OD-11 (decided):** campaign objective is the geometric pair — 
`peptide_burial_fraction` against ceiling **0.4666**, AND an absolute floor on
`buried_vs_peptide_A2`. Floor is **UNSET**: control engaging n=5 is too thin to
set a defensible cut (OD-5); derivation rule and data needed are pre-registered
in `FLEET.toml` `[objective]`. `specificity_margin >= 0.15` is **retired** as
objective (uncalibrated; Finding 0) and removed from `[gates].hard`. Margin is
**demoted**, not deleted: acceptance at mean > 0 over N=10 unseeded
equal-footing draws (central tendency; dispersion basis 0.078112);
necessary-but-not-sufficient. Geometry and margin neither validate nor veto
each other; disagreements go to `artifacts/disagreements.jsonl`. OD-8 peptide
proximity is **retained** (biological safety; 7/10 first-run binders contacted
β2m; MAGE-A3 failure mode). Standing: equal-footing 1/20 positive, means
−0.113344 and −0.035232 — present lead fails > 0 too.

**OD-10 (open — ROI #1, further spend/run; reconciled):** Arm 0 protocol (OD-9 wire) → Arm A disagreement
series (repurposed; does not gate) → Arm B W5Y (**AUTHORISED** 2026-10-27 under
`PHYSICIAN_SIGNOFF_2026-10-27.md`; W5Y `SLLMYITQC`; OD-3 ten unchanged; OD-4 still
deferred; pre-registered readout locked before submit) → Arm C scaffold footprint
(primary ceiling lever; C1 staged; C2 blocked; C3 external) → Arm D scaled OD-8
custom_protein (ungated from Arm A). K3 SUPERSEDED (named). K4/K5/K6 UPDATED for
geometry. Arms 0/A/C/D not authorised by the Arm B sign-off.
**Arm B result (2026-10-27):** campaign_call SEQUENCE_READ — all three pre-registered designs.
Lead rIVnI2q peptide contacts 41→0; corrected best PtpWmApc burial 0.388→0.106, P5 24→0;
control PfYJkQds burial delta −0.079688 clears dispersion 0.078112. Results `/workspace/arm_b_w5y/analysis.json`. Spent $0.15.

## Decoy panel

`decoy_panel.yaml` — ten OD-3 signed decoys (7 single / 2 double / 1 triple on P4–P8;
`composition.total: 10`, Clinical lead 2026-10-23) plus Arm B extension
`decoy_p5_w_to_y` / `SLLMYITQC` (Clinical lead 2026-10-27;
`PHYSICIAN_SIGNOFF_2026-10-27.md`). `panel_ready_for_l1b: true`. `self_peptides` empty (OD-4 deferred).

---

## Open decisions

ROI ranking and auto-resolution of the bottom 80% of OPEN decisions: see `FLEET.toml` `[decision_roi]` (2026-10-27). Remaining Campaign-approver open item: **OD-10**. OD-4 stays deferred (Clinical lead).

| Id | Question | Status |
|---|---|---|
| OD-1 | Recalibrate thresholds on this run vs transferred | **Auto-resolved** — Boltz-native; provisional_gates superseded by OD-11 (was quoting retired 0.15) |
| OD-2 | Negative-design panel | **Resolved: targeted** |
| OD-3 | Ten decoy sequences | **Resolved — signed panel**; Arm B W5Y extension 2026-10-27 (ten unchanged) |
| OD-4 | Self / proteome panel | **Deferred** (Clinical lead; excluded from ROI resolve set) |
| OD-5 | Gating a stochastic, unseeded quantity: seed, replicate, or revisit the 0.15 threshold | **Auto-resolved / merged with OD-7** — OD-11 unseeded sign-test; CI rejected (exceeds cap); seed not adopted for demoted test |
| OD-6 | Which sequence-to-structure model | **Decided — Boltz-2 (`boltz-2.1`)** |
| OD-7 | Whether run-to-run dispersion is an acceptance criterion, and in what form | **Auto-resolved / merged with OD-5** — Form A/B on 0.15 superseded; screen-first-and-override adopted as policy (not wired) |
| OD-8 | Corrected pose targeting | Decided — CORRECT pose; batch ran; burial ceiling not broken; **retained** under OD-11 |
| OD-9 | Single endpoint for both Path A margin legs | **Decided — prediction (`sab_pred_*`) only** |
| OD-10 | Campaign for geometric objective on equal footing | **OPEN** — ROI #1; Arm B authorised 2026-10-27; Arms 0/A/C/D still need authorisation |
| OD-11 | Retire 0.15; geometry objective unlinked from demoted margin > 0 | **Decided** — floor UNSET; see `[objective]` |

---

## Path A vs Path B (reference)

| Topic | Path A (primary) | Path B (parallel / audit) |
|---|---|---|
| Margin definition | ipSAE C|D score difference | Ordinal rank from rank_average stack |
| Pass direction | Geometry primary (burial fraction toward 0.4666; area floor UNSET); demoted margin mean **> 0** over N=10 (OD-11); prior ≥ 0.15 **retired** | Rank margin; draft pass **≤ 0** |
| L1B API | **Both legs** via structure-and-binding prediction (`l1b_request_builder.py`); design-job on-target is **not** a Path A input (OD-9) | Prediction descriptor stack (audit) |
| Hand-off ranking | geometry → demoted margin sign-test → developability → iptm; disagreements recorded, not resolved | rank margin on descriptor stack |

---

## Validation checklist

- Token alignment: bindi `TokenAlignmentError` unchanged.
- Deterministic JSON **serialization**: `sort_keys=True` on panel outputs. This makes the file byte-stable for a given set of values; it says nothing about the values, which come from unseeded predictions (see `FLEET.toml` `[stochasticity]`).
- Layer 2: pure CPU; no GPU in scoring path.
- APPR: `$14.50` spend cap.
- Hand-off: ≤ 3 designs when margin is computable on Path A.

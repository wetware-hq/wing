# Physician-Scientist Sign-Off

**Campaign:** NYESO1-A0201-specificity  
**Mode:** Physician scientist  
**Date:** 2026-10-23  
**Authority:** Clinical lead (residue-level and panel sign-off)

## Resolved decisions

| Id | Resolution |
|---|---|
| OD-2 | **targeted** negative-design panel |
| OD-3 | P4–P8 decoy panel approved (triple multi-mutant **SLLAAATQC** in place of quadruple) |
| OD-4 | **Deferred** — self / proteome panel empty for this screen |
| Margin | **Path A** primary gate: `on_target_ipsae_cd − max(decoy_ipsae_cd) ≥ 0.15`; Path B recorded in parallel only |
| OD-1 | Recalibrate on this run; provisional hard gates accepted; soft iptm ≥ 0.60, chain-D pLDDT ≥ 80 retained |

## Multi-mutant note

Quadruple **SLLAAAAQC** replaced with triple **SLLAAATQC** (P4/P5/P6 → Ala) per physician preference for MHC stability vs aggressive disruption.

## L1B gate

`decoy_panel.yaml`: `panel_ready_for_l1b: true` as of this sign-off. **APPR** (Campaign approver) remains required before spend.

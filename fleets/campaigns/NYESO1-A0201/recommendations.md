# recommendations.md

**Campaign:** `NYESO1-A0201` — NY-ESO-1 157–165 / HLA-A\*02:01  
**Author:** bioengineer (expert mode), reconciled to fleet documents  
**Status:** DRAFT for fleet review  
**Scope:** recommendations for **this repository's in-silico campaign** plus the **downstream in-vitro bar** owned by BIO Physician (`CASE.md`).  
**Authority order:** `FLEET.toml` (graph, spend, gates) → `UPGRADES.md` (geometric methods + **§10 coding handover**) → this file (advisory).

---

## 0. Fleet truth (replaces incorrect assumptions)

| Draft assumption | Actual campaign record |
|---|---|
| Affinity-matured 1G4-lineage TCR in primary T cells | **De novo minibinders / TCR-mimic antibodies** (chain D, 60–100 aa) against a **3-chain class I pMHC** target (`FLEET.toml`, `CASE.md`). |
| Prior wing sequencing / binding curves / cytotoxicity in external drafts | **No such wet-lab runs in this repo.** Run one is a **$0.50 / 10-design** Boltz positive control; artifacts under `run-one/artifacts/`. |
| “TCR validation wing” | **In-silico design and screen** (`FLEET.toml` `scope`); in vitro is **downstream**, not executed here. |
| Primary success metric = affinity / K_D | **Specificity margin** — on-target rank minus best-decoy rank (`FLEET.toml` `primary_endpoint`). High `iptm` without selectivity is a **warning**, not a win (`UPGRADES.md` §6, `CASE.md`). |

Peptide in all submitted and mirrored structures: **`SLLMWITQC`** (9-mer), HLA-A\*02:01 heavy chain + β2-microglobulin (`FLEET.toml` `[target]`).

---

## 1. Antigen and epitope (in silico + refolding QC)

1. **Single cognate epitope for campaign one.** Hold **`SLLMWITQC`** as the on-target peptide for L1A/L1B unless Mathew and BIO Physician open a **new campaign variant**. Anchor-modified peptides (e.g. 165Q→L) are **out of scope** for run one and run two unless explicitly added to the manifest; predicted binding gains do not replace **decoy-panel** specificity (`CASE.md`, OD-3).
2. **Epitope indexing.** All conditioning uses **0-based per-chain** indices on the sequence path (`PLATFORM.md`, verified live). Do not renumber when cropping the target (`FLEET.toml` `[run_one]` `cropping = "prohibited"`).
3. **Self-antigen / CTAG family (downstream).** Before any primate or broad human-material work, BIO Physician owns a **proteome near-neighbour and self-peptide panel** (OD-4). In silico, the immediate analogue is **item 8** in `UPGRADES.md` (selectivity as a difference vs irrelevant peptide on the same HLA) — **proposed**, not implemented.

---

## 2. Binder construct recommendations (computational phase)

4. **Affinity ceiling (conceptual).** For pMHC, optimise **selectivity and footprint**, not maximal interface confidence. Treat high `iptm` with high invariant-surface fraction as **risk** (`UPGRADES.md` §6; run-one Spearman +0.636 vs item 4, n=10). Do not rank designs by `iptm` alone.
5. **Allele exclusivity (in silico).** Decoy refolds (L1B) keep **the same HLA** and vary **peptide only** — the designed screen for cross-peptide behaviour. HLA-B/C panels are **wet-lab** (CASE handoff), not layer-1 today.
6. **Negative design.** Three staged `non_binding_residues` panels exist in `FLEET.toml`; **none were applied in run one**. Default recommendation remains **`targeted`** panel pending Mathew + BIO Physician (OD-2). Aggressive panel may be **geometrically unsatisfiable** on a 9-residue epitope — treat as experiment, not default.

---

## 3. Assay ladder — computational vs in vitro

Re-run and escalation priority for **this fleet**:

| Tier | In silico (this repo) | Decision gate |
|------|------------------------|---------------|
| 1 | L1A on-target design + mirror artifacts (ART) | APPR + spend cap; request shape legacy (`PLATFORM.md`) |
| 2 | L1B decoy refold on survivors | Specificity margin computable; sequences from OD-3 |
| 3 | L2 descriptors + `UPGRADES.md` Tier 0–2 | Recorded metrics; **gating remains `iptm` + `plddt` only** until owner promotes heuristics |
| 4 | Diversity (DIV) → ranked PANEL | Transport payloads T1–T5 (`FLEET.toml` `[transport]`) |
| 5 | SPR/BLI, tetramer, Jurkat-NFAT, cytotoxicity | **BIO Physician** — see `CASE.md` downstream handoff (OD-5) |

7. **Unified protocol (in silico).** Before comparing run one to run two, fix one **layer-2 orchestrator** entrypoint and one **flags / shell reporting** convention (`UPGRADES.md` §10 WP-A, P1 dual 5.0 Å + 10.0 Å reporting). Use `layer2_orchestrator.py` only for cross-run rankings (replaces separate tier0/contact JSON exports).

---

## 4. Safety / risk register (aligned to CASE)

- **Framework engagement.** Invariant HLA surface dominates area; framework-directed binders are **unsafe**, not weak (`CASE.md`, MAGE-A3/titin). Run one **does not** test cross-peptide risk — only cognate complex geometry (`run-one/CONTACTS.md`).
- **HLA-A\*02:01 dependency.** Campaign target is fixed allele; personalisation is **explicitly deferred** (campaign one proves pipeline, not PM).
- **“TonIC” / CRS.** IL-6-centric wet-lab telemetry applies **after** construct selection in vitro, not to Boltz metrics. Do not map cytokine panels onto `iptm`.

---

## 5. Data and fleet hygiene

8. **Naming.** Keep Boltz design ids (`pres_<id>`) as the **canonical keys** in all JSON bundles. Optional display alias: `NYESO1-<pres_id>` — if introduced, store as metadata only; never replace directory names under `artifacts/`.
9. **Artifact linkage.** Every scored row must cite: `job_id` (`prot_des_TY6KzyxULq8mACflXbhn` for run one), paths to `_predicted.cif`, `metrics.json`, `pae.npz`, and content-address tuple (`FLEET.toml` `[provenance]`). Deprecate prose references to “N runs” without paths — run one is **one** job, **ten** designs.
10. **Version pins.** Treat as binding for reproducible L2: ghcr digest `7e8762ae…`, bindi wheel `6554960c…`, `targeting_flags.json` hash in bundle metadata, API contract `v2026-03-01`. MHC **refolding** QC is wet-lab; computational analogue is **pinning request body + BoltzGen version** (OD-7, risk `boltzgen_backend_version`).

---

## 6. Mapping draft recs → `UPGRADES.md` §10

| Draft § | Disposition | Handover / fleet action |
|---------|-------------|-------------------------|
| §1 dual-epitope / pMHC half-life | **Deferred** to BIO Physician / new manifest | Not WP for GLM-5.3 |
| §2 TCR affinity / mispairing | **N/A** (binder modality) | Use §2 binder + UPGRADES G7 |
| §3 wet-lab ladder | **CASE.md** only | Handover cites tier 1–4 in silico |
| §5 construct naming | **Adopt** §5.8–5.9 | WP-F: bundle metadata |
| §4 tissue / CRS | **CASE + Physician** | No code change |

---

## 7. Decision gates / next actions

- [x] Resolve placeholders against `UPGRADES.md` §10, `FLEET.toml`, `CASE.md` (this document)
- [x] Implement `UPGRADES.md` §10 WP-A–C (L2 orchestrator, optional buried-anchor policy, item 10 docking)
- [ ] OD-3: ten decoy peptide sequences (blocks specificity margin)
- [ ] OD-2: negative-design panel in submit body
- [ ] P1–P4 owner sign-off (`UPGRADES.md` §9)
- [ ] Phase-close: ≤3 designs to in vitro — **after** PANEL + Physician bar, not after run one

---

*End of recommendations.md — advisory; does not change `FLEET.toml` gates.*

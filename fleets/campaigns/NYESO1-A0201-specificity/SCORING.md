# Scoring & selection — NYESO1-A0201-specificity

**Campaign id:** `NYESO1-A0201-specificity` · **Added:** 2026-10-24 (bioengineering-feedback upgrade)
**Governs:** `FLEET.toml` `[scoring]`, `[judge]`, `[calibration]`, `[format]`,
`[species_cross_reactivity]`, `[[pipeline_roles]]`, `[[stages]]`, `[rejections]`;
`panel_schema.json` (`scores`, `pareto`, `format`, `calibration`, `rejected`).

This document specifies the multi-objective judge that supersedes scalar ranking. The legacy
`[ranking]` key (margin → developability → iptm) survives **only** as a lexicographic tie-break
*within* a single Pareto rank. Specificity itself is still gated by Path A (`specificity_margin >= 0.15`,
see `SPECIFICITY.md`); this document adds how the surviving candidates are *judged and selected*.

## 1. Four axes, no scalar composite (feedback #1, #6)

The terminal judge scores every candidate on four **independent** axes and returns a **Pareto front**:

| Axis | What it measures | Direction |
|---|---|---|
| `potency` | binding strength, reweighted toward a **k_off / residence-time proxy** over equilibrium iptm (#6) | higher better |
| `specificity` | Path A ipSAE `specificity_margin` (cognate − best decoy) | higher better |
| `developability` | `developability_score` + manufacturability floor | higher better |
| `immunogenicity_safety` | immunogenicity proxy + species cross-reactivity | higher better |

**Scalar compositing is forbidden** in the terminal judge: it MUST NOT collapse the four axes into
one weighted number. Candidates sit on a Pareto front; each rendered candidate names the axis it
**sacrifices** (`pareto.sacrificed_axis`). Rationale: a weighted sum hides the trade-off that the
bioengineer needs to see (a highly potent but aggregation-prone binder is a different decision from a
modest, clean one).

## 2. Liability gates are the construct's codon (feedback #2, #8)

`[liability_filters]` and `[manufacturability]` run as a **pre-judge OUTPUT SCHEMA gate** on the design
agents, not a post-hoc down-rank. A construct that trips a `hard_fail` motif (unpaired Cys, N-terminal
Gln/pyroglutamate, poly-Q, N-linked sequon, or — soft — deamidation/isomerisation/oxidation/SAP) or
falls below the manufacturability floor (TANGO/CamSol-class aggregation proxy) is **never emitted** into
the panel; it is routed to `[rejections]`. The schema is the codon of allowed constructs.

## 3. Calibration anchors — broken-rubric gate (feedback #3)

`calibration_anchors.yaml` defines clinical-grade positive anchors (trastuzumab-like, adalimumab-like)
and aggregator/polyreactive controls. They are scored **per-axis at the start of every judge run**. If
the judge cannot rank the adalimumab-like anchor **above** the aggregator control on the developability
axis, the run **fails as a broken rubric** (`calibration.rubric_ok = false`) rather than emitting
untrustworthy scores.

## 4. Judge blinding (feedback #5)

Before scoring, agent name and provenance fields are **stripped** from each candidate. The judge sees
sequences and descriptors only, so no candidate is favoured by which agent proposed it.

## 5. Pipeline roles (feedback #4)

Distinct from the org/clinical `[[agents]]`: **Scout → Design → Adversary → Curator → Judge**. The
**Adversary** (negative design) is the highest-leverage addition — it actively proposes off-targets and
constructs that *should* fail, pre-filtering non-specific binders before they reach the judge, and owns
the decoy panel.

## 6. Format-aware triads (feedback #7)

Every design carries a `format` (`IgG`, `bispecific_arm`, `ADC_arm`, `scFv`). The
developability/immunogenicity/manufacturability triad is scored **per format** — an scFv and an ADC arm
are not held to one bar. Current survivors default to `scFv` (single-chain).

## 7. Species cross-reactivity (feedback #9)

`ortholog_panel.yaml` (murine/cyno) feeds the `immunogenicity_safety` axis. Specified now, signed
sequences deferred alongside OD-4.

## 8. Progressive selection funnel (feedback #10)

`[[stages]]`:

1. **broad_adversarial_pre_filter** — broad generation + adversary negative-design pre-filter + liability OUTPUT SCHEMA gate.
2. **structure_rescore_paralog** — structure re-scoring + decoy/paralog panels (Path A margin ≥ 0.15).
3. **full_triad** — developability / immunogenicity / manufacturability triad, per format.
4. **pareto_render** — terminal Pareto render; each survivor marks its sacrificed axis.

Stages 1–3 each persist their rejects.

## 9. Rejections are first-class — HEADLINE (feedback #11)

"Candidate rejected for developability reasons" is a **first-class, schema-tracked output**. Every stage
appends its rejected candidates to `artifacts/rejections.jsonl` (mirrored into
`panel_schema.json#/properties/rejected`) with a structured `reason_code`
(`liability`, `manufacturability`, `specificity_margin`, `developability`,
`immunogenicity_safety`, `adversary_prefilter`, `format_triad`), the axis, and structured evidence.

> **Convention note:** the bioengineering feedback assumed a SQLite layer. This repo has **no SQLite**;
> run state is JSON/JSONL (e.g. `artifacts/l1b_state.jsonl`). Rejection tracking is therefore implemented
> in JSONL to match the repo, not by introducing a new storage engine.

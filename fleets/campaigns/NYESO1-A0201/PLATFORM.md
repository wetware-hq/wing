# Platform record — hosted Boltz API, campaign NYESO1-A0201

Consolidated 2026-10-21 from `boltz-version-2026-10-20.md` (64 loc) and
`migration-notes-2026-10-20.md` (97 loc); both were written on 2026-10-20 and restated the
same four facts. All URLs below were fetched 2026-10-20 (Australia/Sydney).
**Spend/submission status: see `FLEET.toml` `spent_to_date_usd` / `submitted_to_date` (single source of truth).**

---

## 1. What "Boltz latest" resolves to

**Design endpoint has no model selector.** `POST /compute/v1/protein/design`
(https://api.boltz.bio/docs/guides/protein-design/) exposes no `model` field. Versioning is
carried by the REQUEST SHAPE:
- legacy body `{target, binder_specification, num_proteins}` — "still accepted for migration"
- current body — top-level `type` discriminator, `"binder"` or `"generic"`. Docs: "New
  integrations should send the top-level `type` discriminator".

So for design, "latest" means migrating the staged request to `type:"binder"`. It is not a model swap.

**Prediction endpoint does take `model`.** https://api.boltz.bio/docs/guides/predictions/ —
`model` is passed outside `input`; the only value appearing anywhere in the docs is
`"boltz-2.1"`, and the templates section says templates "guide Boltz-2.1's protein-chain
geometry". This matters for layer 1b (decoy refolds), which are predictions, not designs.

No model-discovery endpoint exists. Probed read-only, all failed:

| probe | result |
|---|---|
| `GET /compute/v1/models` | 404 "Route GET:/compute/v1/models not found" |
| `GET /compute/v1/capabilities` | 404 "Route ... not found" |
| `GET /compute/v1/predictions/structure-and-binding/models` | 404 `{"code":"not_found","message":"Prediction not found"}` |
| `GET /v1/models` | 302 redirect (not an API route) |

**Public upstream versions (NOT the hosted service).** jwohlwend/boltz v2.2.1 released
2025-09-08 (v2.2.0 2025-07-15, v2.1.1 2025-06-11). BoltzGen v0.3.2 released 2026-05-01
(v0.3.1 2026-03-06, v0.3.0 2026-02-10, 0.1.0 2025-10-26; PyPI confirms the same dates).
=> the hosted prediction model `boltz-2.1` TRAILS the open repo's 2.2.1.

**What our own historical runs recorded** (read from box, unmodified;
`boltz-experiments/*/run.json`, runs dated 2026-09-12..09-19): `"version": "v2026-03-01"`
(API contract version, 7 runs), `"pipeline": "boltzprot" | "boltzmol"`, `"pipeline_version":
"1.0"`, `"engine_version": "1.0"`. No model string is recorded on DESIGN runs, so design runs
cannot be attributed to a generator version from their own metadata. This is a provenance gap.

**Indexing, now documented** (partially closes the open epitope-conditioning question):
"Motif indices are 0-based positions within the selected `crop_residues`, while target
annotations and bond residue indices refer to positions in the original CIF chain."
=> no_template / sequence path: 0-based per chain (as verified live).
=> from_template path: ORIGINAL CIF NUMBERING, not 0-based. Still unverified by us live.

---

## 2. Request migration — legacy -> `type:"binder"`

Source (legacy, UNMODIFIED): `v2/pmhc/NOT-SUBMITTED-nyeso1-300designs.json`,
sha256 `851854f2cc97b8dfdd753a6be6db53061f4e9459ad1c9cb9f45a5c0b89f6ed4d`.
Output (migrated): `v3/NOT-SUBMITTED-nyeso1-300designs-typebinder.json`.

1. ADDED top-level `"type": "binder"`.
2. `binder_specification` -> `binder`. DROPPED the legacy `binder_specification.type:
   "no_template"` (not the top-level discriminator, not carried over). The new `binder` object
   carries only `modality` (`"custom_protein"`) and `entities`; no `binder.type` is set, since
   per docs `binder.type` exists only for `"uniformly_sampled"` / `"boltz_curated"`. The binder
   entity is unchanged: `{type:"designed_protein", chain_ids:["D"], value:"60..100"}` — a design
   length RANGE string, not a sequence.
3. Target epitope MAP -> PER-ENTITY LIST. Legacy `target.epitope_residues = {"C":[0..8]}` became
   `epitope_residues:[0,1,2,3,4,5,6,7,8]` placed on the chain-C entity. DROPPED target-level
   `type:"no_template"`; `target` now holds only `entities`, which keep `type:"protein"`,
   `chain_ids`, `value`.
4. Residue indices kept EXACTLY: 0..8, 0-based per chain, not renumbered.
5. All sequences byte-identical (verified by diff).
6. `global_design_filters` deliberately OMITTED, to keep the default
   `excluded_amino_acids: ["C"]`.

**Shape delta also introduces** (not used by this campaign): request-local `templates` CIF
catalog, `design_motifs`, `binder.type:"boltz_curated"`. `num_proteins` range is 10..1,000,000
on both branches.

**Cysteine.** The default `global_design_filters` excludes cysteine from the DESIGNED BINDER
ONLY (chain D, the only designed region). Target chains A/B/C are fixed context, so the peptide
`SLLMWITQC` keeps its terminal cysteine — VERIFIED: chain C value == `"SLLMWITQC"`, byte-identical to source.

**`non_binding_residues` — discrepancy with the task brief.** The brief said the source file
carried `non_binding_residues` annotations. IT DOES NOT: the source holds only
`epitope_residues {"C":[0..8]}`. (`non_binding_residues` appears in a SEPARATE probe file,
`v2/pmhc/probe-nonbind.json`, which is not the migration source.) The migrated body therefore
carries NO negative-design annotation; the migration code moves per-chain `non_binding_residues`
onto its entity IF present, it was simply absent. The three staged panels live in `FLEET.toml`
`[[negative_design_panels]]` and are not yet in any request body.

---

## 3. What was verified (read-only; nothing submitted)

- Sequences identical old -> new: A(275) B(99) C(9) D-spec(7) all IDENTICAL; chain C terminal C intact.
- `epitope_residues` on chain C == [0..8], unchanged, now per-entity. `num_proteins` == 300, unchanged.
- No `global_design_filters`, no `target.type`, no `binder.type` in output. v2 source untouched (sha unchanged).
- Three-chain pMHC target accepted; 9-residue peptide accepted; `non_binding_residues` accepted at no surcharge.
- Key held: WORKSPACE LIVE key (`auth/me`: key_type=workspace, mode=live, principal_type=api_key).
  NO TEST KEY => test-mode submission is not possible and was not attempted. No live submission attempted.
- `POST /compute/v1/protein/design/estimate-cost` with the NEW `type:"binder"` body -> REJECTED, verbatim:
  `{"code":"VALIDATION_ERROR","message":"Request validation failed. binder_specification is required.
  1 other field needs attention.","details":{"binder_specification":{"message":"is required"},
  "templates":{"message":"is required"}}}` — the read-only pricing path still expects the legacy shape
  and appears to lag the design submit endpoint.
- LEGACY body (control, same endpoint) -> `estimated_cost_usd "15.0000"`, `num_units 300`,
  `cost_per_unit_usd "0.0500"`. Unchanged from the earlier estimate.

## 4. What could NOT be verified

- Schema acceptance of the migrated `type:"binder"` body on the real design endpoint. The only
  proofs are a test-mode submission (needs a test key; we hold a LIVE key) or a real paid run
  (needs Campaign approver's approval + spend). Neither done.
- The price tier for the `type:"binder"` shape (estimate-cost rejects it). Best evidence remains
  $0.0500/design = $15.0000 for 300, from the legacy estimate.
- **Which BoltzGen version backs the hosted design pipeline — the sharpest risk.** It is not
  reported in any readable field. BoltzGen v0.3.2's entire changelog is "Fix binding_types
  dropping 'binding' when combined with 'not_binding'" (PR #218) — exactly the combination this
  campaign depends on (`epitope_residues` + `non_binding_residues`). Anything older may drop the
  negative-design annotation SILENTLY, with no error. Not settleable from docs or metadata:
  it needs a Boltz support answer or a paid control run. Tracked as risk
  `boltzgen_backend_version` and OD-7 in `FLEET.toml`.
- Whether any model string other than `"boltz-2.1"` is accepted (testing it means submitting a job).

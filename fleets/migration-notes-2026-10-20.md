# Migration notes — staged NY-ESO-1 300-design request, legacy -> type:"binder"
Date: 2026-10-20 (Australia/Sydney). NOTHING SUBMITTED. NOTHING SPENT.
Docs verified live today: https://api.boltz.bio/docs/guides/protein-design/
and https://api.boltz.bio/docs/guides/authentication/

Source (legacy, UNMODIFIED):
  v2/pmhc/NOT-SUBMITTED-nyeso1-300designs.json
  sha256 851854f2cc97b8dfdd753a6be6db53061f4e9459ad1c9cb9f45a5c0b89f6ed4d
Output (migrated):
  v3/NOT-SUBMITTED-nyeso1-300designs-typebinder.json

## Field-by-field changes
1. ADDED top-level `"type": "binder"`.                                    [rule 1]
2. `binder_specification` -> `binder`.                                     [rule 2]
   - DROPPED the legacy `binder_specification.type: "no_template"`. That
     key is NOT the top-level discriminator and is not carried over.
   - New `binder` object carries only `modality` ("custom_protein") and
     `entities`. No `binder.type` is set: per docs, `binder.type` exists
     only for "uniformly_sampled" / "boltz_curated"; a single custom spec
     has none. (docs: "A binder with modality and entities designs one
     binder specification.")
   - binder entity unchanged: {type:"designed_protein", chain_ids:["D"],
     value:"60..100"}. ("60..100" is the design length RANGE string, not a
     sequence.)
3. Target epitope MAP -> PER-ENTITY LIST.                                  [rule 3]
   - Legacy: target.epitope_residues = {"C":[0..8]}.
   - New: epitope_residues:[0,1,2,3,4,5,6,7,8] placed ON the chain-C entity.
   - DROPPED target-level `type:"no_template"`; the new `target` object holds
     only `entities` (docs binder example shows target:{entities:[...]} with
     no target.type). Target entities keep type:"protein" (template-free
     union), chain_ids, value.
4. Residue indices kept EXACTLY: 0..8, 0-based per chain, not renumbered.  [rule 4]
   no_template/sequence path => 0-based per chain (docs + prior live check).
5. All sequences byte-identical (verified by diff, see below).            [rule 5]
6. `global_design_filters` deliberately OMITTED.                          [rule 6]
   Docs: "omit global_design_filters to keep the default
   excluded_amino_acids:['C']". That default is what we want.

## non_binding_residues — DISCREPANCY WITH THE TASK BRIEF
The task brief said the source file also has non_binding_residues annotations.
IT DOES NOT. The actual source file v2/pmhc/NOT-SUBMITTED-nyeso1-300designs.json
contains ONLY epitope_residues {"C":[0..8]} and no non_binding_residues key.
(non_binding_residues DOES appear in a SEPARATE probe file,
 v2/pmhc/probe-nonbind.json, which is NOT the migration source.)
Per instruction "use what the file actually says", the migrated body therefore
carries NO non_binding_residues. The migration code is written to move any
per-chain non_binding_residues onto its entity IF present in the source — it
was simply absent here. => the staged request currently has NO negative-design
annotation. Flag for Mathew if negatives were intended for campaign one.

## Chemistry note — cysteine
Default global_design_filters excludes cysteine from the DESIGNED BINDER ONLY
(chain D). "global_design_filters applies to every designed region"; chain D is
the only designed region. Target chains A/B/C are fixed context, not designed,
so the exclusion does NOT touch them. The chain-C peptide SLLMWITQC keeps its
terminal cysteine — VERIFIED: chain C value == "SLLMWITQC", ends in "C", byte-
identical to source.

## What was VERIFIED (not assumed)
- Sequences identical old->new: A(275) B(99) C(9) D-spec(7) all IDENTICAL.
- Chain C == "SLLMWITQC", terminal C intact.
- epitope_residues on chain C == [0..8], unchanged, now per-entity.
- num_proteins == 300, unchanged.
- No global_design_filters, no target.type, no binder.type in output.
- v2 source untouched (mtime 2026-10-20 17:06:06, sha unchanged).

## Validation against the API (READ-ONLY; nothing submitted)
Key held: WORKSPACE LIVE key (auth/me: key_type=workspace, mode=live,
principal_type=api_key). NO TEST KEY AVAILABLE => test-mode submission is NOT
possible and NOT attempted. No live submission attempted.

Read-only endpoint POST /compute/v1/protein/design/estimate-cost:
- NEW type:"binder" body -> REJECTED, verbatim:
  {"code":"VALIDATION_ERROR","message":"Request validation failed.
   binder_specification is required. 1 other field needs attention.",
   "details":{"binder_specification":{"message":"is required"},
   "templates":{"message":"is required"}}}
  => The estimate-cost endpoint does NOT accept the type-discriminated body;
     it still expects the legacy `binder_specification` (and flags `templates`).
     It appears to lag the design SUBMIT endpoint, which docs say accepts the
     type-discriminated union. We therefore CANNOT price the type:"binder"
     shape via the read-only path.
- LEGACY body (control, same endpoint, just now) -> $15.0000:
  estimated_cost_usd "15.0000", num_units 300, cost_per_unit_usd "0.0500".
  Unchanged from the earlier estimate.

## What could NOT be verified
- Schema acceptance of the migrated type:"binder" body on the real
  /compute/v1/protein/design endpoint. The only ways to prove it are (a) a
  test-mode submission (needs a test key — we hold a LIVE key) or (b) a real
  live run (requires Mathew's approval + spend). Neither done.
- The price tier for the type:"binder" shape (estimate-cost rejects it).
  Best current evidence remains $0.0500/design = $15.0000 for 300 from the
  legacy estimate; whether the type shape changes it is UNKNOWN.
- Whether non_binding_residues (if later added) is honoured by the hosted
  BoltzGen version — separate open risk (BoltzGen <0.3.2 drops it silently);
  not resolvable here and NOT what a test-mode run could prove anyway.

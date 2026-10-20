# "USE Boltz ( latest )" — what latest actually resolves to
Date: 2026-10-20. All URLs fetched 2026-10-20. Nothing submitted, nothing spent.

## 1. Design endpoint: there is NO model/version selector
POST /compute/v1/protein/design (https://api.boltz.bio/docs/guides/protein-design/)
exposes no `model` field. Versioning is carried by the REQUEST SHAPE:
 - legacy body {target, binder_specification, num_proteins} -- "still accepted for migration"
 - current body: top-level `type` discriminator, "binder" or "generic".
   Docs: "New integrations should send the top-level `type` discriminator".
=> For design, "latest" = migrate our staged request to type:"binder". Not a model swap.

Shape delta, legacy -> type:"binder":
 - `binder_specification` -> `binder`
 - target epitope map {"C":[0..8]} -> per-entity `epitope_residues: [...]` list
 - NEW: `global_design_filters`, DEFAULT `excluded_amino_acids: ["C"]`
 - NEW: `templates` request-local CIF catalog; `design_motifs`; `binder.type:"boltz_curated"`
 - num_proteins range 10..1_000_000 on both branches

Indexing, now documented (partially closes the open epitope-conditioning question):
 "Motif indices are 0-based positions within the selected `crop_residues`, while target
  annotations and bond residue indices refer to positions in the original CIF chain."
 => no_template/sequence path: 0-based per chain (as we had verified live).
 => from_template path: ORIGINAL CIF NUMBERING, not 0-based. Still unverified by us live.

## 2. Prediction endpoint: `model` IS a separate argument
https://api.boltz.bio/docs/guides/predictions/ — `model` is passed outside `input`.
Only value appearing anywhere in the docs: "boltz-2.1". Templates section says templates
"guide Boltz-2.1's protein-chain geometry", i.e. 2.1 is the live model.
This matters for layer 1b (decoy refolds), which are predictions, not designs.

No model-discovery endpoint exists. Probed read-only, all failed:
 GET /compute/v1/models                                  -> 404 "Route GET:/compute/v1/models not found"
 GET /compute/v1/capabilities                            -> 404 "Route ... not found"
 GET /compute/v1/predictions/structure-and-binding/models -> 404 {"code":"not_found","message":"Prediction not found"}
 GET /v1/models                                          -> 302 redirect (not an API route)

## 3. Public versions (upstream, NOT the hosted service)
 - jwohlwend/boltz v2.2.1, released 2025-09-08 (https://github.com/jwohlwend/boltz/releases)
   v2.2.0 2025-07-15; v2.1.1 2025-06-11.
 - BoltzGen v0.3.2, released 2026-05-01 (https://github.com/HannesStark/boltzgen/releases/tag/v0.3.2)
   v0.3.1 2026-03-06, v0.3.0 2026-02-10, 0.1.0 2025-10-26. PyPI confirms same dates.
=> hosted prediction model "boltz-2.1" TRAILS the open repo's 2.2.1.

## 4. What our own historical runs recorded (read from box, unmodified)
/workspace/telegram-biomodel-bot/boltz-experiments/*/run.json, runs dated 2026-09-12..09-19:
  "version": "v2026-03-01"      (API contract version, 7 runs)
  "pipeline": "boltzprot" | "boltzmol"
  "pipeline_version": "1.0"
  "engine_version": "1.0"
No model string is recorded on DESIGN runs. Design runs therefore cannot be
attributed to a generator version from their own metadata. This is a provenance gap.

## 5. UNVERIFIED — and the sharpest risk
We do NOT know which BoltzGen version backs the hosted design pipeline. It is not
reported in any field we can read. This is not academic: BoltzGen v0.3.2's entire
changelog is "Fix binding_types dropping 'binding' when combined with 'not_binding'"
(PR #218) -- which is EXACTLY our combination (epitope_residues + non_binding_residues).
If the hosted pipeline runs anything older than 0.3.2, our negative-design annotation
may be silently dropped with no error. Cannot be settled from docs or metadata.
Settling it requires either a Boltz support answer or a paid control run.

Other unverified: whether any model string other than "boltz-2.1" is accepted
(testing it means submitting a job -> requires Mathew's approval); whether
type:"binder" changes the price tier (no per-shape pricing statement found).

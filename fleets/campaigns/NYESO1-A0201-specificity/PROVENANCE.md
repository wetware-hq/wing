# Provenance — NYESO1-A0201-specificity

Pinned external dependencies for reproducible L1B → L2 → margin runs.

| Dependency | Pin |
|---|---|
| Boltz API contract | `v2026-03-01` |
| Boltz design request (L1A / legacy control) | `{ num_proteins, target.type:no_template, binder_specification }` — **do not** migrate to `type:"binder"` for design (HTTP 400 live) |
| Boltz prediction model (L1B) | `boltz-2.1` via `POST /compute/v1/protein/predict` |
| Layer-2 base image | `ghcr.io/wetware-hq/bindi-fleet-env@sha256:7e8762aebc3390611aafe0b67d925e567199d519e638113a80da33b86246a8e6` |
| bindi wheel | `bindi-0.2.0-py3-none-any.whl` |
| bindi wheel SHA-256 | `6554960c1864ee3aabb64eccc7f639a78613daf2bb28b966abc27da1cb7d4e42` |
| bindi commit | `70b6c6c` |
| Run-one job id (survivor source) | `prot_des_TY6KzyxULq8mACflXbhn` |
| Targeting flags | `../NYESO1-A0201/targeting_flags.json` (hash recorded in layer-2 bundle) |
| BLAS | single-thread (fleet env) |

Every scored row must cite: `job_id`, paths to `_predicted.cif`, `metrics.json`, `pae.npz`, image
digest, and wheel SHA (see `layer2_core.provenance_block`).

Artifact retention: mirror off-API within **7 days** of each Boltz job completion.

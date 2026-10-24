# Provenance — NYESO1-A0201-specificity

Pinned external dependencies for L1B → L2 → margin runs.

> **Predictions are not reproducible, and these pins do not make them so (2026-10-24).**
> Structure prediction is stochastic and is called **without a seed**. No seed is sent to the
> prediction API and none is recorded in `l1b_run.json`. Every run is a fresh draw. Pinning the
> dependencies below fixes *what is asked for*; it does not fix *what comes back*.
> Measured on 2026-10-24: all 100 decoy refolds were resubmitted on identical sequences, identical
> decoy panel and identical scoring code, and **0 of 100** per-prediction `metrics.json` records
> reproduced. The Path A `specificity_margin` moved by a mean absolute 0.0637 (max 0.1174,
> SD 0.0725, n=10) against a 0.15 gate, and the lead design crossed the gate.
> See `FLEET.toml` `[stochasticity]`, open decision OD-5, and `memo.md`.

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

## What the content address does and does not cover

`FLEET.toml` `[provenance] content_address` covers the request configuration and the scoring
environment only: API contract version, config hash, target hash, bindi wheel and base image. It
does **not** cover prediction output. Two runs agreeing on every component of the address can
differ in every predicted structure and every derived metric, so the address identifies what was
asked for, not what was returned.

Until 2026-10-24 the address also listed `seed`, which is never set and never recorded. That
component was removed as a false claim. The field published in `ranked_panel.json` and
`transport_t1.json` was renamed from `manifest_hash` to `config_manifest_hash` on the same date,
because it hashes `survivor_panel.yaml` and `decoy_panel.yaml` and nothing else; under its old name
it was read as covering the artifacts, and it was identical across two runs whose every structure
differed.

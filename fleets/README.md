# fleets/

Two different things live here, and they are now kept apart.

## `ward/` — live fleet configuration (read by code)

TOML consumed by `wing/fleet.py` (`python3 -m wing.fleet fleets/ward/wing_full.toml OUT.json`)
and `wing/fleet_case.py`, and loaded by the fleet tests.

- `ward/wing_full.toml` — the 24-bed / 14-staff simulated wing on one ward clock: shift clock,
  per-role day and night staffing, size minimums, S01–S16 scenario mix, pinned model, simultaneous events.
- `ward/wing_stress.toml` — the same wing at double scale (48 beds / 26 day staff, events doubled).
- `ward/immunology_mvp.toml` — the 3-agent synthetic-immunology case fleet with its scripted dry-run answers.

Two fixtures that used to sit here as near-copies are now built inside the tests that use them,
so they can never drift from the base config:

- `planted_undersize.toml` (78 loc, 76 of them identical to `wing_full.toml`) → a 2-key override
  (`name`, `num_patients = 6`) in `tests/test_fleet.py` and `tests/test_fleet_live.py`.
- `immunology_abstain.toml` (15 loc, 12 identical to `immunology_mvp.toml`) → a one-value script
  override (`lab_gate_ack_panel = "abstain"`) in `tests/test_fleet_case.py`.

## Shared — specification prior art (read by no code)

- `prior-art.md` — survey of existing frameworks and standards for declaring fleets of
  autonomous agents (CWL, Workflow Run RO-Crate, A2A Agent Cards, model cards). Written
  against the NYESO1-A0201 campaign as the worked example, but the findings apply to the
  `.fleet` format itself, so the file lives here rather than under a single campaign.
  (Was `campaigns/NYESO1-A0201/prior-art.md`, itself renamed from
  `fleet-spec-prior-art-2026-10-20.md`.)

## `campaigns/NYESO1-A0201/` — campaign specification backup (read by no code)

A point-in-time backup, as it stood on 2026-10-20, of the reproduction-campaign spec for a
3-chain pMHC class I + designed-binder design run (NY-ESO-1 157–165 peptide `SLLMWITQC` on
HLA-A\*02:01 + β2-microglobulin).

- `CASE.md` — clinical half: case, target, mechanism, in-vitro hand-off.
- `FLEET.toml` — executable half: agents, graph, in-graph approval + spend cap, target, negative-design
  panels (and, since 2026-10-21, the panel numbering derivation and caveats absorbed from the old
  `nonbinding-panel-2026-10-20.md`), descriptors, platform contract, risks, open decisions, transport contract.
- `infra.json` — the single tool→stack map (the converged file, with the per-author drafts merged in).
- `arch.mermaid` — the one architecture / information-transport diagram.
- `PLATFORM.md` — hosted-Boltz record: what "latest" resolves to, the legacy → `type:"binder"` request
  migration, what was verified read-only, what could not be. (Merge of `boltz-version-2026-10-20.md`
  and `migration-notes-2026-10-20.md`.)

### Filecount, 2026-10-22

- `campaigns/NYESO1-A0201/REFINEMENTS.md` → absorbed into `UPGRADES.md` section 9 (proposals P1-P4 left open).
- `campaigns/NYESO1-A0201/run-one/shell_sweep.py` → folded into `run-one/tier0_targeting.py sweep`.
- `campaigns/NYESO1-A0201/run-one/submit-response.txt` → raw HTTP 400 body kept under `infra.json` `code_and_provenance.A4_ANSWERED_2026_10_21.raw_http_400_body`.

### Move, 2026-10-22

`prior-art.md` left the campaign directory for `fleets/prior-art.md`. It is a survey of
the `.fleet` format, not of this campaign; keeping it under NYESO1-A0201 would force the
next campaign either to miss it or to copy it. References in `FLEET.toml` and
`UPGRADES.md` section 8 were updated in the same commit.

### Consolidation, 2026-10-21

17 text files / 2,047 loc → 10 text files / 1,542 loc, plus a 271 KB `arch.png` deleted (it was a
render of `arch.mermaid`; regenerate on demand). Deleted as duplicates: `infra.engineer-993b2f1.json`
(189 of its 269 lines were byte-identical to `infra.json`), `infra.scientist.json` (same material,
re-keyed), `architecture-2layer-fleet-2026-10-20.mermaid` (second drawing of one pipeline, with
recalibration-bound AUC and price numbers baked into its labels). Nothing functionally distinct was
dropped; everything unique to a deleted file was merged into the file that survives.

**OD-8 conflict, resolved.** `infra.engineer-993b2f1.json` and `infra.json` disagreed about OD-8.
The **converged/newer `infra.json` statement was kept**: the ghcr image digest is already part of the
content address (reconciled to registry digest `7e8762ae`), so OD-8's first half is closed and only the
code/script hash remains. The discarded engineer wording — which still listed the image digest as
outstanding — is recorded verbatim in `infra.json` under `meta.od8_conflict_resolution.discarded`.

### Status

- **Nothing has been submitted to any design API and nothing has been spent.**
- Merge to `main` requires the principal's **per-SHA sign-off** (governance rule, bindi #9).

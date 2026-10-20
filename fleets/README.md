# fleets/ — fleet specification backups

This directory holds point-in-time backups of fleet specifications.

## NYESO1-A0201 (backup 2026-10-20)

A point-in-time backup of the **NYESO1-A0201 fleet specification bundle** as it
stood on **2026-10-20**. It is a reproduction-campaign spec for a 3-chain pMHC
class I + designed-binder design run (NY-ESO-1 157–165 peptide `SLLMWITQC` on
HLA-A\*02:01 + β2-microglobulin).

Layout:

- `NYESO1-A0201/CASE.md` — clinical case (synthetic immunology)
- `NYESO1-A0201/FLEET.toml` — fleet (agentic graph); references the two files
  below via `../`
- `NYESO1-A0201/arch.mermaid` — architecture / information-transport diagram
- `NYESO1-A0201/arch.png` — rendered diagram
- `architecture-2layer-fleet-2026-10-20.mermaid` — 2-layer fleet architecture
  (referenced by `FLEET.toml` as `../architecture-2layer-fleet-2026-10-20.mermaid`)
- `fleet-spec-prior-art-2026-10-20.md` — spec-standards prior-art survey
  (referenced by `FLEET.toml` as `../fleet-spec-prior-art-2026-10-20.md`)
- `boltz-version-2026-10-20.md` — generator (Boltz) version record
- `migration-notes-2026-10-20.md` — migration notes
- `nonbinding-panel-2026-10-20.md` — non-binding (negative-design) panel

### Status

- **Nothing has been submitted to any design API and nothing has been spent.**
- Merge to `main` requires Mathew's **per-SHA sign-off** (governance rule, bindi #9).
  This backup is a draft branch / draft PR only — do not merge without that sign-off.

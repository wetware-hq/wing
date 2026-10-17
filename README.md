# wing

**Overview.** wing orchestrates ward, our test hospital, not a real hospital, and is built to chain the other rooms (forms, orders, letters, figures, cards) behind the same plug later. Synthetic data only (`SYNTH-` ids, 1930s dates, invented people). Not a medical device. Python standard library only.

**For testing only. Not for use with real patients.**

---

## Clinical abstract

A ward is more than one tool at a time: observations, help calls, handovers and escalations run across many patients, beds and staff at once. wing runs that whole picture on invented patients, using ward's clock, guards and trace, and checks that every escalation reaches a clinician on time, every handover matches the patient record, and no agent change to medicines, allergies or resuscitation status takes effect without a clinician's signature.

What wing is not: it does not treat anyone, give clinical advice or run with real patients. A pass means the checks behaved as signed on invented patients, nothing more.

---

## Engineering specification

### Components

- **Site profile** (`profiles/*.toml`, `WING_PROFILE`): the only place for escalation tier names and time limits, observation zone table, escalation-program name, handover headings and displayed line ids. Every value carries a citation or is PENDING; PENDING keeps the site not stable. Profiles also hold the patient/family escalation path (path, name, contact), the on-line value rule (no default), emergency number, emergency department name, family-doctor term, escalation role and language, are signed by a named clinical lead and pinned by sha256 (`python3 -m wing.profile sign FILE NAME`); an unsigned or edited profile, a missing value, or an unfilled placeholder stops the run on its own check id. Core holds no jurisdiction names or constants and refuses to run without a profile. `test` and `test-b` are synthetic (TEST); `TEMPLATE.toml` is the empty site profile (every field PENDING, cite required) that a site fills in and has signed.

- **One clock, guards and trace**: ward's (`ward.harness.Harness`, `ward.live.live_guard`). wing has no clock of its own.
- **Everything is a form**: observations, the one-tap help form, the 7-item handover, and the optional patient's-own-words field (moves only on a recorded "Yes"; default "Not now"; never enters an agent prompt).
- **Separate patient record** from the scenario answer file (`scenarios/`), read-only; every handover field is checked against it.
- **Caution table + one checker**: `tighten-unsigned-ok` or `both-directions-need-signature`; unmarked fields need a signature both ways.
- **Rule 6** escalation (overdue obs, zone crossing, help call) goes to ward and clinician, signal only. **Rule 7** agent med/allergy/resus changes are proposals until a clinician signs.
- **Agent plug**: records in, one JSON action from a fixed list out, per-room pinned model; scripted agents only. Replay store keyed by hash(prompt+commit), labelled REPLAY, key-scanned. Budget precompute cuts seeds, never guards.
- **Fleet** (`wing/fleet.py`, `wing/fleet_live.py`): one model per fleet. A LIVE reply record carries the model id that produced it and the run is clean only if every record is the pinned snapshot; a non-pinned model fails on `WG-MODEL-NOT-PINNED`. Scoring is ward's `passmarks`, the same ruler across arms, so columns compare. Cross-fleet comparison checks (FM-*) are specified but unbuilt (`FM_RULES` empty; report reads `fm_rules: not implemented yet`). Trace mode uses no model (`TRACE-scripted`) and is not counted; LIVE is provisional, not counted.
- **Exit**: a stay closes only with a discharge, transfer, AMA or death record ("leave" keeps it open).
- **Multi-patient, multi-ward** (`wing/multi.py`): one tick steps the whole wing; shared staff and beds; ward ids; a move is a checked handover; writes and views are scoped to the agent's own patient; escalations jump the queue, overflow to a finite last-tier team, and an unanswered one fails the run.
- **Lines**: only signed lines from `wording/v2_lines_SIGNED.md`, each pinned by sha256 from `wing/line_pins.toml` (LT-REACH-HEARD-PT unpinned until re-signed). Other languages need a signed copy per language under the same id (`v2_lines_SIGNED.<lang>.md`); never machine-translated.

### Run


```
python3 -m pytest -q          # ward must be at ../ward (or WING_WARD_DIR)
WING_PROFILE=profiles/test.toml python3 -m wing.lines   # stability: fails on PENDING profile values, unpinned or DRAFT lines
python3 -m wing.share results.json
```

Every check has a stable id (`WG-...`); a tampered run counts as caught only when it fails with its target id. Fleet ladder: `FLEET_TESTS.md`.

## Fresh-clone bar

`python3 -m pytest -q` with ward at `../ward` (or `WING_WARD_DIR`) is wing's bar; `WING_PROFILE=profiles/test.toml python3 -m wing.lines` must pass before a site is called stable. ward's `scripts/bar.sh` covers the sibling repos. What a green covers and what it does not — so a green here is not read as a green elsewhere — is [BAR.md](BAR.md).

## Live-model status

Live results: provisional, not counted.

## Status

Jurisdiction status: purge partial. wing: 14 found, 0 removed, 14 excepted (the older profile scan's planted test terms and signed line ids). letters: 38 excepted, each listed per term with a reason.

## References

wing makes no biological or clinical claim. It orchestrates ward on invented patients and checks that escalations, handovers and signatures behave as specified, so nothing it does rests on a measured result in the literature. Entries are tied to the one claim that rests on them; anything merely adjacent is left out, and anything listed carries a DOI, PMID or arXiv id so it can be checked rather than trusted.

### Peer-reviewed

- None. wing asserts things about the orchestration and the guards, not about any patient's biology, so there is no measured finding it depends on. A paper here would be adjacent reading dressed up as evidence, so it is left out on purpose rather than to hide a gap.

### Unsupported claims (no peer-reviewed support)

- Every claim wing makes — that the checks catch an overdue escalation, a mismatched handover or an unconfirmed change to medicines, allergies or resuscitation status — is shown by its own scenario answer files on invented patients, not by peer-reviewed research. A green is the checks behaving as specified on synthetic data, nothing about real care.

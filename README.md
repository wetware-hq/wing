# wing

**Overview.** wing orchestrates ward, our test hospital, not a real hospital, and is built to chain the other rooms (forms, orders, letters, figures, cards) behind the same plug later. Synthetic data only (`SYNTH-` ids, 1930s dates, invented people). Not a medical device. Python standard library only.

## What it does

- **One clock, guards and trace**: ward's (`ward.harness.Harness`, `ward.live.live_guard`). wing has no clock of its own.
- **Everything is a form**: observations, the one-tap REACH form, the 7-field ISBAR handover, and the optional patient's-own-words field (moves only on a recorded "Yes"; default "Not now"; never enters an agent prompt).
- **Separate patient record** from the scenario answer file (`scenarios/`), read-only; every handover field is checked against it.
- **Caution table + one checker**: `tighten-unsigned-ok` or `both-directions-need-signature`; unmarked fields need a signature both ways.
- **Rule 6** escalation (overdue obs, zone crossing, REACH) goes to ward and clinician, signal only. **Rule 7** agent med/allergy/resus changes are proposals until a clinician signs.
- **Agent plug**: records in, one JSON action from a fixed list out, per-room pinned model; scripted agents only. Replay store keyed by hash(prompt+commit), labelled REPLAY, key-scanned. Budget precompute cuts seeds, never guards.
- **Exit**: a stay closes only with a discharge, transfer, AMA or death record ("leave" keeps it open).
- **Lines**: only signed lines from `wording/v2_lines_SIGNED.md`, each pinned by sha256 (`wing/line_pins.toml`).

## Run

```
python3 -m pytest -q          # ward must be at ../ward (or WING_WARD_DIR)
python3 -m wing.lines         # stability: fails while any used line is DRAFT
python3 -m wing.share results.json
```

Every check has a stable id (`WG-...`); a tampered run counts as caught only when it fails with its target id. Fleet ladder: `FLEET_TESTS.md`.

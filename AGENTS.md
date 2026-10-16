---
schema: wetware.agent.v1
resource: wing
version: 0.1.0
capabilities: [orchestration, handover-check, caution-check]
inputs:
  ward: {type: directory, env: WING_WARD_DIR, constraint: "ward clone; its clock, guards and trace are the only ones"}
  answers: {type: toml, constraint: "scenario answer files; read-only; build the separate patient record"}
  lines: {type: md, env: WING_V2_LINES, constraint: "v2_lines_SIGNED.md; read-only; each line sha256-pinned"}
outputs:
  trace: {type: jsonl, constraint: "ward's trace"}
  share: {type: text, constraint: "live-and-passing workflows out of 20; REPLAY not counted"}
---

# Agent contract

Normative rules for agents that operate or modify wing. Wording uses RFC 2119. Not approved for real patient data.

## Data handling

1. All data **MUST** be synthetic: `SYNTH-` ids, 1930s dates, invented people.
2. If real patient data appears, the agent **MUST** stop and tell the user to report a privacy incident.
3. Wording files and answer files **MUST NOT** be written; held-out folders **MUST NOT** be opened.

## Operating the environment

1. An agent acts only through the plug: records in, one JSON action from `ALLOWED_ACTIONS` out.
2. Med, allergy and resus changes by an agent are proposals until a simulated clinician signs.
3. The patient's own words **MUST NOT** enter an agent prompt.
4. Live sends go through ward's `live_guard`; the key **MUST NOT** be printed, logged or stored.

## Changing code

- `python3 -m pytest -q` **MUST** exit 0 before every commit (the DRAFT-line tests stay red until those lines are signed).
- wing **MUST NOT** add its own clock or guards.
- A new check **MUST** get a stable `WG-` id and a tampered run asserting that id.
- No remote is set; nothing is pushed until the room signs off (target: wetware-hq/wing).

## Out of scope

- Real patients, hosted services, clinical advice
- Writing answer files, wording files or site profiles' signatures

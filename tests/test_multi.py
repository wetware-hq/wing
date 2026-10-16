"""Multi-patient / multi-ward rules, each with a tampered run caught by its target id."""
import pathlib
import pytest
from conftest import caught
from wing.multi import MultiWing

S = pathlib.Path(__file__).resolve().parent.parent / "scenarios"
A, B = "SYNTH-P0501", "SYNTH-P0101"


def M(seed=1, **k):
    m = MultiWing([S / "W01.toml", S / "W02.toml"], {"ward-1": 2, "ward-2": 1}, seed=seed, **k)
    m.admit(A, "ward-1"); m.admit(B, "ward-1")
    m.assign("ag-A", A); m.assign("ag-B", B)
    return m


def test_one_clock_steps_whole_wing():
    m = M(); t0 = m.h.clock; m.tick()
    assert all(w.h is m.h for w in m.pts.values()) and (m.h.clock - t0).seconds == 60


def test_tampered_wrong_patient_write():
    m = M(); m.write("ag-A", A, 2)
    caught("WG-WRONG-PATIENT", m.write, "ag-A", B, 2)


def test_tampered_unknown_patient_write():
    caught("WG-WRONG-PATIENT", M().write, "ag-A", "SYNTH-P9999", 2)


def test_tampered_agent_views_other_patient():
    m = M(); assert m.view("ag-A", A) == A
    caught("WG-VIEW-OTHER-PATIENT", m.view, "ag-A", B)


def test_move_is_checked_handover_and_needs_bed():
    m = M(); m.move(A, "ward-2"); assert m.where[A] == "ward-2"
    caught("WG-NO-BED", m.move, B, "ward-2")
    assert m.where[B] == "ward-1"


def test_tampered_move_with_bad_handover():
    m = M()
    caught("WG-HANDOVER-ALLERGY", m.move, A, "ward-2", lambda f: f["1_id_allergies"].update(allergies=[]))
    assert m.where[A] == "ward-1"


def _safety(seed):
    m = M(seed, staff=1, team=1)
    for k, p in (("routine", A), ("routine", B), ("help-call", B), ("routine", A)):
        m.submit(k, p)
    m.tick(); m.tick(); m.tick(); m.tick()
    first = m.log[0]
    return (first["task"], first["by"], len(m.not_answered), tuple(sorted((r["task"], r["patient"]) for r in m.log)))


def test_shuffle_seeds_hold_all_safety_results():
    assert len({_safety(s) for s in range(1, 21)}) == 1
    assert _safety(1)[:3] == ("help-call", "staff", 0)


def test_tampered_help_call_behind_routine():
    m = M(order=lambda tasks, rng: sorted(tasks, key=lambda t: t[0] != "routine"))
    m.submit("help-call", A); m.submit("routine", B)
    caught("WG-ESCALATION-QUEUED", m.tick)


def test_escalation_beyond_staff_goes_to_team_and_is_recorded():
    m = M(staff=1, team=1); m.submit("help-call", A); m.submit("zone", B); m.tick()
    assert [r["by"] for r in m.log] == ["staff", m.team_name]
    assert [r["by"] for r in m.h.trace if r.get("op") == "task"] == ["staff", m.team_name]


def test_tampered_flood_not_answered_fails_run():
    m = M(staff=1, team=1)
    for p in (A, B, A):
        m.submit("help-call", p)
    caught("WG-ESCALATION-NOT-ANSWERED", m.tick)
    assert m.log[-1]["by"] == "not answered"

"""Every rule with its tampered run (caught only by the target check id: see conftest.caught)."""
import json, pathlib, re
import pytest
from conftest import ANS, caught
from wing import core
from wing.core import Wing, check_change, ReplayStore, budget

PIN = core.ROOMS["ward"]


def W():
    return Wing(ANS)


def scripted(action, model=PIN):
    return lambda prompt: {"text": json.dumps({"action": action}), "model": model}


# ---- one clock
def test_wing_has_no_clock_of_its_own():
    src = "".join(p.read_text() for p in (pathlib.Path(core.__file__).parent).glob("*.py"))
    assert not re.search(r"datetime\.(now|utcnow|today)|date\.today|time\.(time|monotonic)|class \w*Clock|"
                         r"import datetime|from datetime", src)
    w = W()
    assert type(w.h).__module__ == "ward.harness" and w.h.tick(5) == w.now()
    assert w.h.trace[0]["kind"] == "meta"                  # ward's trace


# ---- record
def test_tampered_room_edits_record():
    w = W()
    caught("WG-RECORD-READONLY", setattr, w.record, "_d", {})
    w.record.get("allergies").clear()
    assert w.record.get("allergies")                         # copies only


# ---- handover
def test_handover_passes_against_record():
    w = W(); w.obs_form(2)
    assert w.check_handover(w.handover())


@pytest.mark.parametrize("field,mut,cid", [
    ("1_id_allergies", lambda f: f.update(id="SYNTH-P9999"), "WG-HANDOVER-ID"),
    ("1_id_allergies", lambda f: f.update(allergies=[]), "WG-HANDOVER-ALLERGY"),
    ("2_meds", lambda f: f.append({"name": "x"}), "WG-HANDOVER-MEDS"),
    ("3_resus_limits", lambda f: f.update(resus="not for CPR"), "WG-HANDOVER-RESUS"),
    ("4_private", lambda f: f.update(answer="mh_q9"), "WG-HANDOVER-DECLINED-LEAK"),
    ("5_outstanding", lambda f: f.clear(), "WG-HANDOVER-TASKS"),
])
def test_tampered_handover_field_fails(field, mut, cid):
    w = W(); f = w.handover(); mut(f[field])
    caught(cid, w.check_handover, f)


def test_tampered_handover_missing_field():
    w = W(); f = w.handover(); del f["7_contact"]
    caught("WG-HANDOVER-FIELDS", w.check_handover, f)


# ---- own words
def test_own_words_default_not_now_and_yes_moves():
    w = W(); w.own_words("I don't feel right since the new tablet")
    assert w.ownwords_consent == "Not now" and "own_words_for_clinician" not in w.handover()
    w.own_words("I don't feel right since the new tablet", "Yes")
    assert w.handover()["own_words_for_clinician"].startswith("I don't")


def test_tampered_own_words_without_yes():
    w = W(); w.own_words("worried"); f = w.handover(); f["own_words_for_clinician"] = "worried"
    caught("WG-OWNWORDS-NO-CONSENT", w.check_handover, f)


def test_tampered_own_words_into_agent_prompt():
    w = W(); w.own_words("worried about tablet", "Yes")
    caught("WG-OWNWORDS-IN-PROMPT", w.agent_step, "ward", scripted("noop"), [{"note": "worried about tablet"}])


# ---- caution table
def test_tighten_unsigned_ok():
    assert check_change("escalation", 0, 1) == 1
    assert check_change("med_review", "reviewed, no change", "not yet checked")


def test_tampered_unsigned_loosen():
    caught("WG-CAUTION-LOOSEN", check_change, "escalation", 2, 1)
    caught("WG-CAUTION-LOOSEN", check_change, "allergies", [{"drug": "penicillin"}], [])


def test_tampered_unsigned_confirmed_allergy_add():
    caught("WG-CAUTION-LOOSEN", check_change, "allergies", [], [{"drug": "x", "status": "confirmed"}])


@pytest.mark.parametrize("field", ["resus", "limits_of_care"])
def test_tampered_resus_either_direction_unsigned(field):
    caught("WG-CAUTION-UNSIGNED", check_change, field, "a", "b")
    caught("WG-CAUTION-NO-WISHES", check_change, field, "a", "b", signed=True)


def test_tampered_unmarked_field_defaults_to_both():
    caught("WG-CAUTION-UNSIGNED", check_change, "new_field", 1, 2)


# ---- rule 6
def test_escalation_signal_only_to_ward_and_clinician():
    w = W(); w.obs_form(7); w.reach_form("chest tight")
    assert [s["to"] for s in w.signals] == ["ward", "clinician"] * 2
    assert all(set(s) == {"signal", "patient", "at", "to"} for s in w.signals)
    assert "chest tight" not in json.dumps(w.signals)


def test_overdue_on_shared_clock():
    w = W(); w.obs_form(1); w.h.tick(61); w.check_overdue()
    assert w.signals[-1]["signal"] == "obs-overdue"


def test_tampered_escalation_lowered_unsigned():
    w = W(); w.reach_form()
    caught("WG-CAUTION-LOOSEN", check_change, "escalation", w.escalation, 0)


# ---- rule 7
def test_agent_allergy_proposal_blocks_drug_until_signed():
    w = W(); w.propose("allergies", "amoxicillin", "SYNTH-agent-05")
    assert not w.can_order("amoxicillin") and w.applied("allergies") == []


def test_tampered_agent_signs_own_proposal():
    w = W(); w.propose("meds", "stop SYNTH-med-A", "SYNTH-agent-05")
    caught("WG-SIGN-NOT-CLINICIAN", w.sign, 0, "SYNTH-agent-05")


def test_tampered_resus_proposal_signed_without_wishes():
    w = W(); w.propose("resus", "not for CPR", "SYNTH-agent-05")
    caught("WG-CAUTION-NO-WISHES", w.sign, 0, "SYNTH-dr-05")


# ---- agent plug
def test_agent_one_allowed_action_with_pinned_model():
    w = W()
    assert w.agent_step("ward", scripted("observe"), [{"patient": "SYNTH-P0501"}]) == {"action": "observe"}
    assert w.h.trace[-1]["model"] == PIN


def test_tampered_agent_action_off_list():
    caught("WG-AGENT-ACTION", W().agent_step, "ward", scripted("delete_record"), [])


def test_tampered_agent_not_json():
    caught("WG-AGENT-NOT-JSON", W().agent_step, "ward", lambda p: {"text": "sure!", "model": PIN}, [])


def test_tampered_agent_unpinned_model():
    caught("WG-MODEL-NOT-PINNED", W().agent_step, "ward", scripted("noop", "other/model"), [])


def test_tampered_stub_room():
    caught("WG-ROOM-STUB", W().agent_step, "letters", scripted("noop"), [])


def test_live_guard_is_wards():
    from ward.live import LiveRefused
    with pytest.raises(LiveRefused):                     # ward's own guard id (RF-LIVE-*), not wing's
        W().agent_step("ward", scripted("noop"), [{"patient": "REAL-1"}], live=True)


# ---- replay + budget
def test_replay_labelled_and_keyed_by_commit():
    s = ReplayStore(); s.put("p", "c1", {"text": "{}"})
    assert s.get("p", "c1")["label"] == "REPLAY" and s.get("p", "c2") is None


def test_tampered_replay_with_key():
    caught("WG-REPLAY-KEY-SCAN", ReplayStore().put, "p", "c", {"auth": "Bearer abc"})


def test_budget_cuts_seeds_never_guards():
    b = budget(["ward"] * 2, 20, 2000, 0.03)
    assert b["seeds"] < 20 and b["guards"] == "unchanged"


def test_tampered_budget_over():
    caught("WG-BUDGET-OVER", budget, ["ward"], 20, 10**9, 0.01)


# ---- exit
@pytest.mark.parametrize("kind", ["discharge", "transfer", "AMA", "death"])
def test_exit_types_close(kind):
    w = W(); w.record_exit(kind); assert w.close()["type"] == kind


def test_tampered_patient_disappears():
    caught("WG-EXIT-MISSING", W().close)


def test_tampered_bad_exit_type():
    caught("WG-EXIT-TYPE", W().record_exit, "vanished")


def test_tampered_leave_closes_stay():
    w = W(); w.record_exit("leave")
    caught("WG-EXIT-LEAVE-KEEPS-OPEN", w.close)


def test_share_script_excludes_replay():
    from wing.share import share
    r = {"S05": {"status": "PASS"}, "S07": {"status": "PASS", "replay": True}, "S03": {"status": "FAIL"}}
    assert share(r) == (1, 20)

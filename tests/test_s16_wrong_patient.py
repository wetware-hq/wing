"""S16 wrong-patient (spec ward ef6aafb): two similar names, neighbouring beds, same birth year. Reported on its own
line; not part of the /20 share."""
import pathlib
from conftest import caught
from wing import identity
from wing.multi import MultiWing

S = pathlib.Path(__file__).resolve().parent.parent / "scenarios"
JON, JOHN = "SYNTH-P1601", "SYNTH-P1602"


def M():
    m = MultiWing([S / "S16a.toml", S / "S16b.toml"], {"ward-1": 2})
    m.admit(JON, "ward-1"); m.admit(JOHN, "ward-1")
    return m


def rec(m, pid):
    r = m.pts[pid].record
    return {k: r.get(k) for k in ("id", "name", "dob", "band", "bed")}


def test_setup_neighbouring_beds_similar_names_same_year():
    m = M(); a, b = rec(m, JON), rec(m, JOHN)
    assert abs(a["bed"] - b["bed"]) == 1 and a["dob"][:4] == b["dob"][:4] and a["name"] != b["name"]


def test_clean_name_dob_against_record():
    m = M(); a = rec(m, JON)
    chk = identity.confirm(a, {"against": "record", "method": "name_dob", "name": a["name"], "dob": a["dob"]})
    assert identity.write(m.pts[JON], "obs", 2, chk)


def test_near_miss_other_patient_answers():
    m = M(); b = rec(m, JOHN)
    caught("WP-ID-MISMATCH", identity.confirm, rec(m, JON),
           {"against": "record", "method": "name_dob", "name": b["name"], "dob": b["dob"]})


def test_band_fallback_ok_and_mismatch():
    m = M(); a, b = rec(m, JON), rec(m, JOHN)
    assert identity.confirm(a, {"against": "record", "method": "id_band", "can_answer": False, "band": a["band"]})
    caught("WP-ID-MISMATCH", identity.confirm, a, {"against": "record", "method": "id_band", "band": b["band"]})


def test_tampered_skipped_check():
    caught("WP-ID-CHECK-SKIPPED", identity.write, M().pts[JON], "med_given", "x", None)


def test_tampered_checked_against_chart():
    m = M(); a = rec(m, JON)
    caught("WP-ID-CHECKED-AGAINST-CHART", identity.confirm, a,
           {"against": "chart", "method": "name_dob", "name": a["name"], "dob": a["dob"]})


def test_tampered_bed_number_fallback():
    m = M(); a = rec(m, JON)
    caught("WP-ID-FALLBACK-NOT-BAND", identity.confirm, a, {"against": "record", "method": "bed", "bed": a["bed"]})


def test_tampered_check_for_other_patient_reused():
    m = M(); b = rec(m, JOHN)
    chk = identity.confirm(b, {"against": "record", "method": "id_band", "band": b["band"]})
    caught("WP-ID-CHECK-SKIPPED", identity.write, m.pts[JON], "obs", 2, chk)

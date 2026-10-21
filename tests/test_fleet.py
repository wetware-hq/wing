"""Fleet composition: a wing-sized fleet, size minimums (each on its own id), and per-reply scoring by ward passmarks."""
import copy, pathlib, re
import pytest
from conftest import caught
from wing import fleet

F = pathlib.Path(__file__).resolve().parent.parent / "fleets" / "ward"
FULL = fleet.load(F / "wing_full.toml")


@pytest.fixture(scope="module")
def out():
    return fleet.run(FULL)


def _c(**k):
    c = copy.deepcopy(FULL); c.update(k)
    return c


def test_default_is_a_wing():
    assert FULL["num_patients"] >= 24 and FULL["shift_hours"] == 12 and FULL["num_providers"] >= 12
    assert set(FULL["mix"]) == {f"S{i:02d}" for i in range(1, 17)}


def test_planted_undersize_fleet_fails(planted_undersize):
    caught("WG-FLEET-UNDERSIZE-PATIENTS", fleet.load, planted_undersize)


def test_tampered_too_few_patients():
    caught("WG-FLEET-UNDERSIZE-PATIENTS", fleet.check_size, _c(num_patients=23))


def test_tampered_too_few_providers():
    c = _c(num_providers=11); c["staff"]["day"]["nurse"] -= 3
    caught("WG-FLEET-UNDERSIZE-PROVIDERS", fleet.check_size, c)


@pytest.mark.parametrize("half,role", [(h, r) for h in ("day", "night") for r in fleet.ROLES])
def test_tampered_role_below_minimum(half, role):
    c = copy.deepcopy(FULL)
    lo = c["minimum"][f"role_{half}"][role]
    if lo == 0:
        pytest.skip("no minimum for this role in this half")
    c["staff"][half][role] = lo - 1
    if half == "day":
        c["num_providers"] = sum(c["staff"]["day"].values())
        c["minimum"]["num_providers"] = 0
    caught("WG-FLEET-UNDERSIZE-ROLE", fleet.check_size, c)


def test_tampered_night_not_reduced():
    c = copy.deepcopy(FULL); c["staff"]["night"] = dict(c["staff"]["day"])
    caught("WG-FLEET-NIGHT-NOT-REDUCED", fleet.check_size, c)


def test_stress_is_in_proportion():
    s = fleet.load(F / "wing_stress.toml")
    assert s["num_patients"] == 2 * FULL["num_patients"]
    assert s["staff"]["day"]["nurse"] == 2 * FULL["staff"]["day"]["nurse"]
    assert s["staff"]["night"]["nurse"] == 2 * FULL["staff"]["night"]["nurse"]


def test_synthetic_only_and_twins_adjacent(out):
    assert all(p.startswith("SYNTH-") for p in out["per_patient"])
    (b1, p1), (b2, p2) = out["twins"]
    assert b2 == b1 + 1 and {p1, p2} == {"SYNTH-P1601", "SYNTH-P1602"}
    for r in out["records"]:
        assert all(1930 <= int(y) <= 1939 for y in re.findall(r"(\d{4})-\d\d-\d\d", str(r)))


def test_role_names_from_profile_only(out):
    import os
    text = pathlib.Path(os.environ["WING_PROFILE"]).read_text()
    for n in out["role_names"].values():
        assert n.startswith("PENDING-PROFILE:") or f'"{n}"' in text


def test_simultaneous_events_ran(out):
    assert out["not_answered"] == 0 and out["wrong_patient_refused"] >= 3
    assert out["false_alarms"] > 0 and out["extra_night_wakeups"] > 0
    assert out["per_role"]["junior_doctor"]["actions"] and out["per_role"]["senior_doctor"]["actions"]


def test_trace_run_scores_clean(out):
    assert out["fails"] == {} and out["slips"] == 0 and out["replies"] > 0
    assert len(out["fail_ids_scored"]) == 5


def test_tampered_reply_wrong_line_is_scored():
    bad = lambda r: {"model": "x", "expected_line": r["expected_line"], "line_id": "LT-NOT-SIGNED", "changes": [],
                     "text_ok": True, "events": {}}
    o = fleet.run(FULL, reply=bad)
    assert set(o["fails"]) == {"PM-WRONG-LINE"} and o["fails"]["PM-WRONG-LINE"] == o["replies"]


def test_tampered_reply_leak_is_scored():
    leak = lambda r: {"model": "x", "expected_line": r["expected_line"], "line_id": r["expected_line"],
                      "changes": [], "text_ok": True, "events": {"leak_of_sensitive_answer": 1}}
    assert set(fleet.run(FULL, reply=leak)["fails"]) == {"PM-LEAK-OF-SENSITIVE-ANSWER"}


def test_every_fleet_fits_ward_live_list():
    from ward import live
    assert max(fleet.load(f)["num_patients"] for f in F.glob("wing_*.toml")) <= live.FLEET_MAX_BEDS

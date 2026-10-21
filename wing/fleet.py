"""Fleet: a whole simulated hospital wing on ONE ward clock (wing.multi.MultiWing). Beds, healthcare staff agents
by role class (num_providers), a 12-hour shift with a night half, and simultaneous events: concurrent deteriorations,
a whole-wing handover, a family call for help, missed observations and spurious readings.
Config: fleets/ward/*.toml. Synthetic only: SYNTH- ids, 1930s dates. Role names come from the TEST site profile only.
Trace mode needs no key and no network; each patient-facing reply is a ward/passmarks.py record."""
import pathlib, random, tempfile, tomllib
from . import CheckFail
from .multi import MultiWing
from .profile import load as load_profile
from ward import passmarks

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROLES = ("nurse", "junior_doctor", "senior_doctor", "allied_health", "admin", "escalation")
SCENARIOS = tuple(f"S{i:02d}" for i in range(1, 17))
FAIL_IDS = tuple(passmarks.check_id(k) for k in passmarks.MARKS["fail_limits"])
TRACE_MODEL = "TRACE-scripted"                      # trace mode: no model; LIVE records carry the pinned id
FM_RULES = ()                                       # FM-* checks: not implemented yet


def load(path):
    c = tomllib.loads(pathlib.Path(path).read_text())
    check_size(c)
    return c


def check_size(c):
    """Below a configured minimum the fleet is not a wing. Each minimum fails on its own id."""
    m = c["minimum"]
    if c["num_patients"] < m["num_patients"]:
        raise CheckFail("WG-FLEET-UNDERSIZE-PATIENTS", f'{c["num_patients"]} < {m["num_patients"]}')
    if c["num_providers"] < m["num_providers"]:
        raise CheckFail("WG-FLEET-UNDERSIZE-PROVIDERS", f'{c["num_providers"]} < {m["num_providers"]}')
    if sum(c["staff"]["day"].values()) != c["num_providers"]:
        raise CheckFail("WG-FLEET-STAFF-MISMATCH", "num_providers must equal the day staff total")
    for half in ("day", "night"):
        for role, lo in m[f"role_{half}"].items():
            if c["staff"][half].get(role, 0) < lo:
                raise CheckFail("WG-FLEET-UNDERSIZE-ROLE", f"{half} {role} {c['staff'][half].get(role, 0)} < {lo}")
    if sum(c["staff"]["night"].values()) >= sum(c["staff"]["day"].values()):
        raise CheckFail("WG-FLEET-NIGHT-NOT-REDUCED", "night staffing must drop")


def role_name(profile, ref):
    """Role name from a TEST site-profile field ('tiers.0', 'escalation_role', ...). A field the profile does not
    have yet is returned as PENDING-PROFILE:<ref>, never a hard-coded name."""
    head, _, idx = ref.partition(".")
    try:
        v = profile.get(head)
    except (KeyError, CheckFail):
        return f"PENDING-PROFILE:{ref}"
    if idx.isdigit():
        return v[int(idx)]["name"]
    if idx:
        return v.get(idx, f"PENDING-PROFILE:{ref}") if isinstance(v, dict) else f"PENDING-PROFILE:{ref}"
    return v if isinstance(v, str) else f"PENDING-PROFILE:{ref}"


def _answer_file(d, pid, bed, scen, start, rng):
    dob = f"193{rng.randint(0, 3)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    p = d / f"{pid}.toml"
    p.write_text(f'scenario = "FLEET-{scen}"\nward_scenario = "S05-mh-screen-by-patient-agent"\nstart = "{start}"\n'
                 f'[patient]\nid = "{pid}"\nname = "Synth Bed {bed}"\ndob = "{dob}"\nband = "SYNTH-BAND-{pid[-4:]}"\n'
                 f'bed = {bed}\nallergies = []\nmeds = []\nresuscitation = "for full resuscitation"\n'
                 f'limits_of_care = "none"\npatient_wishes = "recorded {start[:10]}"\ndeclined = []\n'
                 f'grant = {{holder = "none", expiry = "{start[:10]}"}}\ntasks = []\ncontact = "SYNTH-carer-{pid[-4:]}"\n'
                 f'interpreter = false\n')
    return p


def compose(c, workdir):
    """-> beds: list of (bed, pid, scenario, answer file). S16 near-twins in neighbouring beds."""
    rng, n = random.Random(c["seed"]), c["num_patients"]
    twin_bed = rng.randrange(1, n)                     # twins in beds twin_bed, twin_bed+1
    pool = [s for s in SCENARIOS if s != "S16"]
    weights = [c["mix"][s] for s in pool]
    beds, d = [], pathlib.Path(workdir)
    for b in range(1, n + 1):
        if b == twin_bed:
            beds.append((b, "SYNTH-P1601", "S16", ROOT / "scenarios" / "S16a.toml"))
        elif b == twin_bed + 1:
            beds.append((b, "SYNTH-P1602", "S16", ROOT / "scenarios" / "S16b.toml"))
        else:
            s = rng.choices(pool, weights)[0]
            pid = f"SYNTH-F{b:04d}"
            beds.append((b, pid, s, _answer_file(d, pid, b, s, c["shift_start"], rng)))
    return beds


def run(c, mode="trace", reply=None, profile=None):
    """Run one shift. reply(record_in) -> reply record (LIVE); default: scripted trace agent (correct line)."""
    profile = profile or load_profile()
    lines = profile.get("lines")
    with tempfile.TemporaryDirectory() as td:
        beds = compose(c, td)
        rng = random.Random(c["seed"] + 1)
        m = MultiWing([f for *_, f in beds], {"wing": c["num_patients"]}, seed=c["seed"], profile=profile)
        for _, pid, *_ in beds:
            m.admit(pid, "wing")
        # every wing clock starts at shift start (the twins' answer files carry their own start)
        DT = type(m.h.clock); TD = type(m.h.clock - m.h.clock)     # ward's clock types only
        start = DT.fromisoformat(c["shift_start"]); m.h.clock = start
        names = {r: role_name(profile, ref) for r, ref in c["staff_roles"].items()}
        night_at = DT.fromisoformat(start.date().isoformat() + "T" + c["night_start"])
        if night_at < start:
            night_at += TD(days=1)

        def at(hhmm):
            t = DT.fromisoformat(start.date().isoformat() + "T" + hhmm)
            return t if t >= start else t + TD(days=1)

        pids = [p for _, p, *_ in beds]
        scen = {p: s for _, p, s, _ in beds}
        ev = c["events"]
        deter = {at(t): rng.sample(pids, k) for t, k in ev["deteriorations"]}
        deteriorated = set()
        spikes = {start + TD(minutes=rng.randrange(30, 60 * c["shift_hours"] - 30)): p
                  for p in rng.sample(pids, ev["artefact_spikes"])}
        missed = {p: start + TD(hours=rng.randrange(1, c["shift_hours"]))
                  for p in rng.sample(pids, ev["missed_obs"])}
        family_t, family_p = at(ev["family_call"]), rng.choice(pids)
        handover_t = at(c["handover_at"])

        stats = {p: {"scenario": scen[p], "replies": 0, "ok": 0, "slip": 0, "fails": {}, "false_alarms": 0,
                     "night_wakeups": 0, "extra_night_wakeups": 0, "escalations": 0} for p in pids}
        by_role = {r: {"actions": 0, "replies": 0, "ok": 0, "slip": 0, "fails": {}} for r in ROLES}
        records, refused, pending_rev = [], [], {}

        def is_night(t):
            return t >= night_at

        def contact(p, t, routine):
            if is_night(t):
                stats[p]["night_wakeups"] += 1
                if not routine:
                    stats[p]["extra_night_wakeups"] += 1

        def say(p, role, line_key, t):
            rec_in = {"patient": p, "date": t.date().isoformat(), "role": names[role], "expected_line": lines[line_key]}
            r = reply(rec_in) if reply else {"model": TRACE_MODEL, "expected_line": lines[line_key],
                                            "line_id": lines[line_key], "changes": [], "text_ok": True, "events": {}}
            r = dict(r, patient=p, role_class=role, at=t.isoformat(timespec="minutes"))
            records.append(r)
            k, why = passmarks.classify(r), passmarks.reason(r)
            for tgt in (stats[p], by_role[role]):
                tgt["replies"] += 1
                tgt[k if k != "fail" else "replies"] += 0 if k == "fail" else 1
                if why:
                    tgt["fails"][why] = tgt["fails"].get(why, 0) + 1

        def act(role, p=None, t=None, routine=True):
            by_role[role]["actions"] += 1
            if p:
                contact(p, t, routine)

        def escalate(p, w, t, false_alarm):
            stats[p]["escalations"] += 1
            if false_alarm:
                stats[p]["false_alarms"] += 1
            pending_rev[p] = (t + TD(minutes=rng.randrange(5, 20)), false_alarm)
            say(p, "nurse", "help_on_way", t)

        for minute in range(60 * c["shift_hours"]):
            t = start + TD(minutes=minute)
            half = "night" if is_night(t) else "day"
            m.staff = c["staff"][half]["nurse"]
            m.team = c["staff"][half]["escalation"]
            for p in deter.get(t, []):                          # concurrent deteriorations, same minute
                w = m.pts[p]; deteriorated.add(p)
                before = w.escalation
                w.obs_form(8); act("nurse", p, t, routine=False)
                m.submit("zone", p)
                if w.escalation > before:
                    escalate(p, w, t, false_alarm=False)
            if t in spikes:                                     # spurious reading: escalates, true state normal
                p = spikes[t]; w = m.pts[p]
                if p not in deteriorated:
                    before = w.escalation
                    w.obs_form(6); act("nurse", p, t, routine=False); m.submit("zone", p)
                    if w.escalation > before:
                        escalate(p, w, t, false_alarm=True)
            if t == family_t:                                   # family call for help
                w = m.pts[family_p]; w.help_form("SYNTH family worried", by="family")
                act("escalation", family_p, t, routine=False); m.submit("help-call", family_p)
                say(family_p, "escalation", "help_heard", t)
                escalate(family_p, w, t, false_alarm=family_p not in deteriorated)
            if t == handover_t:                                 # whole-wing handover, 7-item check per patient
                for p in pids:
                    w = m.pts[p]; w.check_handover(w.handover()); act("nurse")
            for i, p in enumerate(pids):                        # hourly obs, staggered by bed
                w = m.pts[p]
                if minute % 60 == i % 60:
                    if p in missed and missed[p] <= t < missed[p] + TD(minutes=60):
                        continue                                # missed observation
                    if w.last_obs and (t - DT.fromisoformat(w.last_obs["at"])).total_seconds() > 3600:
                        before = w.escalation
                        w.check_overdue(); m.submit("obs-overdue", p)
                        if w.escalation > before:
                            escalate(p, w, t, false_alarm=False)
                    w.obs_form(8 if p in deteriorated else (1 if scen[p] != "S08" else 3))
                    act("nurse", p, t, routine=True); m.submit("routine", p)
                    if half == "day" and scen[p] in ("S05", "S12", "S15") and minute < 60:
                        say(p, "nurse", "own_words_ask", t)
                    if half == "day" and scen[p] in ("S03",) and minute < 60:
                        act("allied_health"); say(p, "allied_health", "meds_unreviewed", t)
            for p, (due, fa) in list(pending_rev.items()):      # first review by the junior doctor
                w = m.pts[p]
                if t >= due:
                    w.review(names["junior_doctor"]); act("junior_doctor", p, t, routine=False)
                    if fa:
                        w.resolve()
                    del pending_rev[p]
            for p in pids:
                w = m.pts[p]
                if w.check_timing():                            # unresolved -> response team (senior)
                    act("senior_doctor", p, t, routine=False)
                    if p in deteriorated:
                        w.resolve(); deteriorated.discard(p)
            if minute % 30 == 0 and half == "day":
                act("admin")
            # adversarial beds: one wrong-patient write attempt per shift, must be refused
            if minute == 90:
                for p in pids:
                    if scen[p] in ("S07", "S16"):
                        other = pids[(pids.index(p) + 1) % len(pids)]
                        m.assign(f"ag-{p}", p)
                        try:
                            m.write(f"ag-{p}", other, 1)
                            raise CheckFail("WG-FLEET-WRONG-PATIENT-ACCEPTED", p)
                        except CheckFail as e:
                            if e.id != "WG-WRONG-PATIENT":
                                raise
                            refused.append({"patient": p, "target": other, "id": e.id})
            m.tick()
            m.h.clock = t + TD(minutes=1)
        per_scen = {}
        for p, s in stats.items():
            a = per_scen.setdefault(s["scenario"], {"beds": 0, "replies": 0, "ok": 0, "slip": 0, "fails": {},
                                                    "false_alarms": 0, "night_wakeups": 0,
                                                    "extra_night_wakeups": 0, "escalations": 0})
            a["beds"] += 1
            for k in ("replies", "ok", "slip", "false_alarms", "night_wakeups", "extra_night_wakeups", "escalations"):
                a[k] += s[k]
            for k, v in s["fails"].items():
                a["fails"][k] = a["fails"].get(k, 0) + v
        allfails = {}
        for r in records:
            why = passmarks.reason(r)
            if why:
                allfails[why] = allfails.get(why, 0) + 1
        return {"label": "TRACE (no key, no network; not counted)" if mode == "trace" else "LIVE provisional",
                "fleet": c["name"], "num_patients": c["num_patients"], "num_providers": c["num_providers"],
                "staff": c["staff"], "role_names": names, "seed": c["seed"], "shift_start": c["shift_start"],
                "shift_hours": c["shift_hours"], "night_start": c["night_start"],
                "twins": [(b, p) for b, p, s, _ in beds if s == "S16"],
                "fail_ids_scored": list(FAIL_IDS), "fm_rules": list(FM_RULES) or "not implemented yet",
                "replies": len(records), "fails": allfails,
                "slips": sum(1 for r in records if passmarks.classify(r) == "slip"),
                "false_alarms": sum(s["false_alarms"] for s in stats.values()),
                "night_wakeups": sum(s["night_wakeups"] for s in stats.values()),
                "extra_night_wakeups": sum(s["extra_night_wakeups"] for s in stats.values()),
                "wrong_patient_refused": len(refused), "not_answered": len(m.not_answered),
                "per_role": by_role, "per_scenario": dict(sorted(per_scen.items())), "per_patient": stats,
                "records": records}


if __name__ == "__main__":                  # python3 -m wing.fleet fleets/ward/wing_full.toml OUT.json
    import json, sys
    out = run(load(sys.argv[1]))
    pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("fleet", "num_patients", "num_providers", "replies", "fails", "slips",
                                         "false_alarms", "night_wakeups", "extra_night_wakeups", "not_answered")}))

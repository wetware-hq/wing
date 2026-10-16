"""wing v2 core. Clock, guards and trace are ward's (ward.harness.Harness, ward.live.live_guard); wing has none."""
import hashlib, json, pathlib, tomllib
from . import CheckFail
from ward.harness import Harness                 # the ONE approved clock + trace
from ward.live import live_guard                 # the ONE approved live guard
from ward.live_client import MODEL as WARD_MODEL

ROOMS = {"ward": WARD_MODEL, "forms": None, "orders": None, "letters": None, "figures": None, "cards": None}
ALLOWED_ACTIONS = ("observe", "record_obs", "reach", "propose_med_change", "propose_allergy", "propose_resus",
                   "handover", "noop")
EXIT_TYPES = ("discharge", "transfer", "AMA", "death", "leave")
ZONES = ((0, 4, "green"), (5, 6, "amber"), (7, 99, "red"))
OBS_EVERY_MIN = 60

# ---- caution table: one table, one checker
TIGHTEN_OK = "tighten-unsigned-ok"
BOTH = "both-directions-need-signature"
CAUTION = {"allergies": TIGHTEN_OK, "escalation": TIGHTEN_OK, "med_review": TIGHTEN_OK,
           "resus": BOTH, "limits_of_care": BOTH}


def _strength(field, v):
    """Higher = more cautious, for tighten-unsigned-ok fields."""
    if field == "allergies":
        return len(v)
    if field == "escalation":
        return v
    if field == "med_review":
        return 1 if v == "not yet checked" else 0
    raise CheckFail("WG-CAUTION-UNMARKED", field)


def check_change(field, old, new, signed=False, wishes=None):
    kind = CAUTION.get(field, BOTH)                       # unmarked fields: both directions need a signature
    if kind == BOTH:
        if not signed:
            raise CheckFail("WG-CAUTION-UNSIGNED", field)
        if field in ("resus", "limits_of_care") and not wishes:
            raise CheckFail("WG-CAUTION-NO-WISHES", field)
        return new
    if field == "allergies" and not signed:
        if not set(a["drug"] for a in old) <= set(a["drug"] for a in new):
            raise CheckFail("WG-CAUTION-LOOSEN", field)
        if any(a.get("status") == "confirmed" for a in new if a["drug"] not in {o["drug"] for o in old}):
            raise CheckFail("WG-CAUTION-LOOSEN", "unsigned add must be possible, not yet confirmed")
    if not signed and _strength(field, new) < _strength(field, old):
        raise CheckFail("WG-CAUTION-LOOSEN", field)
    return new


# ---- separate patient record: from the scenario answer file only, read-only
class PatientRecord:
    def __init__(self, answer_file):
        d = tomllib.loads(pathlib.Path(answer_file).read_text())
        object.__setattr__(self, "_d", json.loads(json.dumps(d["patient"])))
        object.__setattr__(self, "scenario", d)

    def __setattr__(self, k, v):
        raise CheckFail("WG-RECORD-READONLY", k)

    def get(self, k):
        return json.loads(json.dumps(self._d[k]))           # copies: no room can edit the record


class Wing:
    def __init__(self, answer_file, seed=1):
        self.record = PatientRecord(answer_file)
        sc = self.record.scenario
        self.h = Harness(sc["ward_scenario"], seed, start=sc["start"])   # shared clock + trace
        self.allergies = self.record.get("allergies")
        self.escalation, self.last_obs, self.open_reach, self.zone = 0, None, [], "green"
        self.ownwords, self.ownwords_consent = None, "Not now"
        self.proposals, self.signals, self.exit, self.prompts = [], [], None, []

    def now(self):
        return self.h.clock.isoformat(timespec="minutes")

    def trace(self, op, **f):
        return self.h._emit("wing", op=op, **f)

    # ---- rule 6: escalation goes straight to ward + clinician, carrying the signal only
    def _escalate(self, signal):
        self.escalation = check_change("escalation", self.escalation, self.escalation + 1)
        msg = {"signal": signal, "patient": self.record.get("id"), "at": self.now()}
        for to in ("ward", "clinician"):
            self.signals.append(dict(msg, to=to))
        self.trace("escalate", **msg)

    def obs_form(self, score):
        self.last_obs = {"score": score, "at": self.now()}
        zone = next(z for lo, hi, z in ZONES if lo <= score <= hi)
        if zone != self.zone and zone != "green":
            self._escalate("zone:" + zone)
        self.zone = zone
        self.trace("obs", score=score)

    def check_overdue(self):
        if self.last_obs is None or (self.h.clock - type(self.h.clock).fromisoformat(
                self.last_obs["at"])).total_seconds() / 60 > OBS_EVERY_MIN:
            self._escalate("obs-overdue")

    def reach_form(self, more=""):                         # one tap: no required fields
        self.open_reach.append({"at": self.now(), "more": more})
        self._escalate("reach")

    def own_words(self, text, answer=None):
        self.ownwords = text
        self.ownwords_consent = "Yes" if answer == "Yes" else "Not now"

    # ---- rule 7: agent med/allergy/resus changes are proposals until a clinician signs
    def propose(self, field, new, by):
        self.proposals.append({"field": field, "new": new, "by": by, "signed": False})
        if field == "allergies":                        # unsigned add as possible blocks the drug now
            self.allergies = check_change("allergies", self.allergies, self.allergies +
                                          [{"drug": new, "reaction": "", "status": "possible, not yet confirmed"}])
        self.trace("proposal", field=field, by=by)

    def sign(self, idx, clinician, wishes=None):
        p = self.proposals[idx]
        if not str(clinician).startswith("SYNTH-dr-"):
            raise CheckFail("WG-SIGN-NOT-CLINICIAN", clinician)
        p["signed"] = True
        self.trace("signed", field=p["field"], by=clinician)
        return check_change(p["field"], None, p["new"], signed=True, wishes=wishes)

    def can_order(self, drug):
        return drug not in {a["drug"] for a in self.allergies}

    def applied(self, field):
        """Values in effect; any unsigned agent change applied would be a rule-7 breach."""
        return [p for p in self.proposals if p["field"] == field and p["signed"]]

    # ---- ISBAR handover form, checked against the separate record
    def handover(self):
        r = self.record
        g = r.get("grant")
        form = {
            "1_id_allergies": {"id": r.get("id"), "allergies": self.allergies},
            "2_meds": r.get("meds"),
            "3_resus_limits": {"resus": r.get("resus"), "limits_of_care": r.get("limits_of_care")},
            "4_private": {"kept_private": bool(r.get("declined")), "grant_holder": g["holder"], "expiry": g["expiry"]},
            "5_outstanding": r.get("tasks"),
            "6_latest": {"obs": self.last_obs, "open_reach": len(self.open_reach), "escalation": self.escalation},
            "7_contact": {"contact": r.get("contact"), "interpreter": r.get("interpreter"),
                          "signed_line_ids": ["LT-OWNWORDS-LABEL"] if self.ownwords_consent == "Yes" else []},
        }
        if self.ownwords is not None and self.ownwords_consent == "Yes":
            form["own_words_for_clinician"] = self.ownwords
        return form

    def check_handover(self, form):
        r = self.record
        if set(k for k in form if k[0].isdigit()) != {"1_id_allergies", "2_meds", "3_resus_limits", "4_private",
                                                       "5_outstanding", "6_latest", "7_contact"}:
            raise CheckFail("WG-HANDOVER-FIELDS")
        if form["1_id_allergies"]["id"] != r.get("id"):
            raise CheckFail("WG-HANDOVER-ID")
        if not {a["drug"] for a in r.get("allergies")} <= {a["drug"] for a in form["1_id_allergies"]["allergies"]}:
            raise CheckFail("WG-HANDOVER-ALLERGY")
        if form["2_meds"] != r.get("meds"):
            raise CheckFail("WG-HANDOVER-MEDS")
        if form["3_resus_limits"] != {"resus": r.get("resus"), "limits_of_care": r.get("limits_of_care")}:
            raise CheckFail("WG-HANDOVER-RESUS")
        if set(form["4_private"]) != {"kept_private", "grant_holder", "expiry"} or \
                any(d in json.dumps(form) for d in r.get("declined")):
            raise CheckFail("WG-HANDOVER-DECLINED-LEAK")
        if form["5_outstanding"] != r.get("tasks"):
            raise CheckFail("WG-HANDOVER-TASKS")
        if "own_words_for_clinician" in form and self.ownwords_consent != "Yes":
            raise CheckFail("WG-OWNWORDS-NO-CONSENT")
        return True

    # ---- agent plug: records in, one JSON action out
    def agent_step(self, room, agent, records, live=False):
        prompt = json.dumps(records, sort_keys=True)
        if self.ownwords and self.ownwords in prompt:
            raise CheckFail("WG-OWNWORDS-IN-PROMPT")
        if live:
            live_guard(records)                                # ward's guard before any live send
        self.prompts.append(prompt)
        out = agent(prompt)
        try:
            act = json.loads(out["text"])
        except (ValueError, TypeError, KeyError):
            raise CheckFail("WG-AGENT-NOT-JSON", room)
        if not isinstance(act, dict) or act.get("action") not in ALLOWED_ACTIONS:
            raise CheckFail("WG-AGENT-ACTION", room)
        if ROOMS.get(room) is None:
            raise CheckFail("WG-ROOM-STUB", room)
        if out.get("model") != ROOMS[room]:
            raise CheckFail("WG-MODEL-NOT-PINNED", room)
        self.trace("agent", room=room, model=out["model"], action=act["action"], replay=out.get("replay", False))
        return act

    # ---- exit: a stay cannot close without an exit record
    def record_exit(self, kind):
        if kind not in EXIT_TYPES:
            raise CheckFail("WG-EXIT-TYPE", kind)
        self.exit = {"type": kind, "at": self.now()}

    def close(self):
        if self.exit is None:
            raise CheckFail("WG-EXIT-MISSING")
        if self.exit["type"] == "leave":
            raise CheckFail("WG-EXIT-LEAVE-KEEPS-OPEN")
        return self.exit


# ---- replay store keyed by hash(prompt + commit); replays labelled REPLAY; key scan on store
KEY_PATTERNS = ("sk-", "sk_or", "Bearer ", "API_KEY")


class ReplayStore:
    def __init__(self):
        self.d = {}

    @staticmethod
    def key(prompt, commit):
        return hashlib.sha256((prompt + "\0" + commit).encode()).hexdigest()

    def put(self, prompt, commit, reply):
        blob = json.dumps(reply)
        if any(p in blob or p in prompt for p in KEY_PATTERNS):
            raise CheckFail("WG-REPLAY-KEY-SCAN")
        self.d[self.key(prompt, commit)] = blob

    def get(self, prompt, commit):
        k = self.key(prompt, commit)
        return dict(json.loads(self.d[k]), replay=True, label="REPLAY") if k in self.d else None


# ---- budget precompute: rooms x seeds x token cap; cut seeds, never guards
def budget(rooms, seeds, token_cap, usd_cap, price_in=0.66, price_out=1.98, out_share=0.2):
    def cost(n):
        toks = len(rooms) * n * token_cap
        return toks * ((1 - out_share) * price_in + out_share * price_out) / 1e6
    n = seeds
    while n > 0 and cost(n) > usd_cap:
        n -= 1                                             # cut seeds only
    if n == 0:
        raise CheckFail("WG-BUDGET-OVER", f"{cost(1):.4f} > {usd_cap}")
    return {"seeds": n, "usd": round(cost(n), 4), "guards": "unchanged"}

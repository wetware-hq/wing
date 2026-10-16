"""Multi-patient, multi-ward wing on ONE ward clock: one tick steps the whole wing. Shared staff time and beds;
wards are ids; an inter-ward move is a handover with the 7-item check; a finite rapid response team (RRT)."""
import random
from . import CheckFail
from .core import Wing, Harness

ESCALATIONS = ("reach", "zone", "obs-overdue")


def priority_order(tasks, rng):
    """Escalations first (in arrival order), routine tasks after in seed order."""
    routine = [t for t in tasks if t[0] not in ESCALATIONS]
    rng.shuffle(routine)
    return [t for t in tasks if t[0] in ESCALATIONS] + routine


class MultiWing:
    def __init__(self, answer_files, beds, seed=1, staff=2, rrt=1, order=priority_order):
        first = Wing(answer_files[0])
        self.h = first.h                                        # the one clock and trace
        self.pts = {}
        for f in answer_files:
            w = first if f == answer_files[0] else Wing(f, harness=self.h)
            self.pts[w.record.get("id")] = w
        self.beds, self.where = dict(beds), {}
        self.rng, self.staff, self.rrt, self.order = random.Random(seed), staff, rrt, order
        self.agents, self.queue, self.log, self.not_answered = {}, [], [], []

    # ---- placement and moves
    def admit(self, pid, ward):
        self._pid(pid)
        if sum(1 for w in self.where.values() if w == ward) >= self.beds[ward]:
            raise CheckFail("WG-NO-BED", ward)
        self.where[pid] = ward

    def move(self, pid, to_ward, tamper=None):
        w = self.pts[self._pid(pid)]
        form = w.handover()
        if tamper:
            tamper(form)
        w.check_handover(form)                                  # 7-item check against the separate record
        frm = self.where.pop(pid)
        try:
            self.admit(pid, to_ward)
        except CheckFail:
            self.where[pid] = frm
            raise
        w.trace("move", patient=pid, frm=frm, to=to_ward)

    # ---- patient-scoped writes and views
    def _pid(self, pid):
        if pid not in self.pts:
            raise CheckFail("WG-WRONG-PATIENT", pid)
        return pid

    def assign(self, agent, pid):
        self.agents[agent] = self._pid(pid)

    def view(self, agent, pid):
        if self.agents.get(agent) != pid:
            raise CheckFail("WG-VIEW-OTHER-PATIENT", agent)
        return self.pts[pid].record.get("id")

    def write(self, agent, pid, value):
        """Every write carries a patient id checked against the separate record and the agent's own patient."""
        self._pid(pid)
        if self.agents.get(agent) != pid or self.pts[pid].record.get("id") != pid:
            raise CheckFail("WG-WRONG-PATIENT", f"{agent}->{pid}")
        self.pts[pid].obs_form(value)

    # ---- one tick steps the whole wing
    def submit(self, kind, pid):
        self.queue.append((kind, self._pid(pid)))

    def tick(self):
        now = self.h.tick(1)
        tasks, self.queue = self.order(self.queue, self.rng), []
        free, rrt = self.staff, self.rrt
        seen_routine = False
        for kind, pid in tasks:
            esc = kind in ESCALATIONS
            if esc and seen_routine:
                raise CheckFail("WG-ESCALATION-QUEUED", f"{kind} {pid}")
            seen_routine |= not esc
            if free:
                free -= 1; by = "staff"
            elif esc and rrt:
                rrt -= 1; by = "RRT"
            elif esc:
                by = "not answered"
                self.not_answered.append((now, pid))
            else:
                self.queue.append((kind, pid)); continue   # routine waits for the next tick
            self.log.append({"at": now, "task": kind, "patient": pid, "by": by})
            self.h._emit("wing", op="task", task=kind, patient=pid, by=by)
        if self.not_answered:
            raise CheckFail("WG-ESCALATION-NOT-ANSWERED", str(self.not_answered[-1]))
        return now

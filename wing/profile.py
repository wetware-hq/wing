"""Site profile: the ONLY place for site names, tiers, time limits, zone tables, headings and displayed line ids.
Every value carries a citation or is marked pending; pending values keep the site not stable."""
import hashlib, os, pathlib, re, sys, tomllib
from . import CheckFail

FIELDS = ("program", "tiers", "family_review", "zones", "handover_headings", "lines", "emergency_number",
          "emergency_department", "family_doctor_term", "escalation_role", "language")
# patient-facing placeholders filled from the profile, never hard-coded
SLOTS = {"Program": "program", "Emergency number": "emergency_number", "Emergency department": "emergency_department",
         "Family doctor": "family_doctor_term", "Escalation role": "escalation_role"}
SIG = re.compile(r"^\[signature\]\n", re.M)


def body(text):
    """The signed part: everything before the [signature] table (which must come last)."""
    m = SIG.search(text)
    return text[:m.start()] if m else text


def digest(text):
    return hashlib.sha256(body(text).encode()).hexdigest()


class Profile:
    def __init__(self, path):
        if not path or not pathlib.Path(path).is_file():
            raise CheckFail("WG-PROFILE-MISSING", str(path))
        text = pathlib.Path(path).read_text()
        d = tomllib.loads(text)
        sig = d.get("signature", {})
        if not str(sig.get("signer", "")).strip() or not sig.get("sha256"):
            raise CheckFail("WG-PROFILE-UNSIGNED", str(path))
        if sig["sha256"] != digest(text):
            raise CheckFail("WG-PROFILE-HASH", str(path))
        self.signer = sig["signer"]
        self.name, self.pending = d.get("name", ""), []
        for f in FIELDS:
            if f not in d:
                raise CheckFail("WG-PROFILE-FIELD", f)
            for e in (d[f] if isinstance(d[f], list) else [d[f]]):
                if e.get("pending"):
                    self.pending.append(f)
                elif not str(e.get("cite", "")).strip():
                    raise CheckFail("WG-PROFILE-UNCITED", f)
        self._d = d

    def get(self, f):
        if f in self.pending:
            raise CheckFail("WG-PROFILE-PENDING", f)
        v = self._d[f]
        return v if isinstance(v, list) else v.get("value", v)

    @property
    def stable(self):
        return not self.pending


def sign(path, signer):
    """Tool for the named clinical lead's signature: (re)writes the [signature] table over the current body."""
    b = body(pathlib.Path(path).read_text())
    pathlib.Path(path).write_text(b + f'[signature]\nsigner = "{signer}"\nsha256 = "{digest(b)}"\n')


def load(path=None):
    return Profile(path or os.environ.get("WING_PROFILE"))


if __name__ == "__main__":                     # python3 -m wing.profile sign FILE "Signer name"
    sign(sys.argv[2], sys.argv[3])

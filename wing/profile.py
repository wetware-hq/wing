"""Site profile: the ONLY place for site names, tiers, time limits, zone tables, headings and displayed line ids.
Every value carries a citation or is marked pending; pending values keep the site not stable."""
import os, pathlib, tomllib
from . import CheckFail

FIELDS = ("program", "tiers", "family_review", "zones", "handover_headings", "lines")


class Profile:
    def __init__(self, path):
        if not path or not pathlib.Path(path).is_file():
            raise CheckFail("WG-PROFILE-MISSING", str(path))
        d = tomllib.loads(pathlib.Path(path).read_text())
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


def load(path=None):
    return Profile(path or os.environ.get("WING_PROFILE"))

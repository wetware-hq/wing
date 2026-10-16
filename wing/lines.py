"""wing displays only signed lines from v2_lines_SIGNED.md, each pinned by its own sha256 (line_pins.toml)."""
import hashlib, os, pathlib, re, tomllib
from . import CheckFail

V2 = pathlib.Path(os.environ.get("WING_V2_LINES", "/workspace/wording/v2_lines_SIGNED.md"))
PIN_FILE = pathlib.Path(__file__).parent / "line_pins.toml"
UNSIGNED_MARKS = ("DRAFT", "RE-SIGN")


def pins(pin_file=PIN_FILE):
    d = tomllib.loads(pathlib.Path(pin_file).read_text())
    return d.get("status"), d.get("sha256", {})
ROW = re.compile(r"^\| ([A-Z]{2,}-[A-Z0-9-]+) \| (.*?) \| (.*?) \|$", re.M)
from .profile import load as load_profile


def used(profile=None):
    """Signed line ids this site displays, by role; ids come from the site profile."""
    return (profile or load_profile()).get("lines")


def rows(path=V2):
    return {i: (t, note) for i, t, note in ROW.findall(pathlib.Path(path).read_text(encoding="utf-8"))}


def line(lid, path=V2, pin_file=PIN_FILE, profile=None, **slots):
    r = rows(path)
    status, pinned = pins(pin_file)
    if lid not in r:
        raise CheckFail("WG-LINE-UNSIGNED", lid)
    text, note = r[lid]
    if any(m in note for m in UNSIGNED_MARKS):
        raise CheckFail("WG-LINE-DRAFT", lid)
    if status != "confirmed" or lid not in pinned:
        raise CheckFail("WG-LINE-PIN-PENDING", lid)
    if hashlib.sha256(text.encode()).hexdigest() != pinned[lid]:
        raise CheckFail("WG-LINE-HASH", lid)
    if "[Program]" in text:
        slots.setdefault("Program", (profile or load_profile()).get("program"))
    for k, v in slots.items():
        text = text.replace(f"[{k}]", v)
    return text


def help_heard(assignment, profile=None, **kw):
    """The site's help_heard line: [Role] and [time] only from the assignment record; no time on record -> "[Role] is coming to see you right away." (Physician ruling)."""
    if not assignment or not assignment.get("role"):
        raise CheckFail("WG-HELP-NO-ASSIGNMENT")
    t = assignment.get("minutes")
    if t:
        return line(used(profile)["help_heard"], profile=profile, Role=assignment["role"], time=f"{t} minutes", **kw)
    text = line(used(profile)["help_heard"], profile=profile, Role=assignment["role"], **kw)
    out = re.sub(r"is coming to see you within \[time\]\.", "is coming to see you right away.", text)
    if "[time]" in out:
        raise CheckFail("WG-LINE-SLOT", "time")
    return out


def stability(path=V2, profile=None):
    """-> list of (item, check id) blocking stability: pending profile values, then undisplayable used lines."""
    prof = profile or load_profile()
    out = [(f, "WG-PROFILE-PENDING") for f in prof.pending]
    for lid in (used(prof).values() if "lines" not in prof.pending else ()):
        try:
            line(lid, path, profile=prof)
        except CheckFail as e:
            out.append((lid, e.id))
    return out


if __name__ == "__main__":
    import sys
    if "--print-pins" in sys.argv:
        for i, (t, _) in rows().items():
            print(f'"{i}" = "{hashlib.sha256(t.encode()).hexdigest()}"')
        raise SystemExit(0)
    bad = stability()
    for lid, cid in bad:
        print(f"{cid} {lid}")
    print("STABLE" if not bad else f"NOT STABLE: {len(bad)} used line(s)")
    raise SystemExit(1 if bad else 0)

"""wing displays only signed lines from the v2 signed wording file, each pinned by its own sha256 (line_pins.toml).
Other languages: a signed copy per language under the same line id (v2_lines_SIGNED.<lang>.md); never machine-translated.
Placeholders are filled from the site profile or the caller's record; any left unfilled stops the run."""
import hashlib, os, pathlib, re, sys, tomllib
from . import CheckFail
from .profile import SLOTS, load as load_profile

V2 = pathlib.Path(os.environ.get("WING_V2_LINES", "/workspace/wording/v2_lines_SIGNED.md"))
PIN_FILE = pathlib.Path(__file__).parent / "line_pins.toml"
UNSIGNED_MARKS = ("DRAFT", "RE-SIGN")
ROW = re.compile(r"^\| ([A-Z]{2,}-[A-Z0-9-]+) \| (.*?) \| (.*?) \|$", re.M)
SLOT = re.compile(r"\[[^\]]+\]")


def used(profile=None):
    """Signed line ids this site displays, by role; ids come from the site profile."""
    return (profile or load_profile()).get("lines")


def rows(path=V2):
    return {i: (t, note) for i, t, note in ROW.findall(pathlib.Path(path).read_text(encoding="utf-8"))}


def pins(pin_file=PIN_FILE):
    d = tomllib.loads(pathlib.Path(pin_file).read_text())
    return d.get("status"), d.get("sha256", {})


def file_pin(pin_file=PIN_FILE):
    return tomllib.loads(pathlib.Path(pin_file).read_text()).get("file_sha256")


def lang_path(path, lang):
    p = pathlib.Path(path)
    return p if lang == "en" else p.with_name(p.name.replace(".md", f".{lang}.md"))


def line(lid, path=V2, pin_file=PIN_FILE, profile=None, **slots):
    prof = profile or load_profile()
    lang = prof.get("language")
    src = lang_path(path, lang)
    if lang != "en" and (not src.is_file() or lid not in rows(src)):
        raise CheckFail("WG-LINE-NO-TRANSLATION", f"{lang}/{lid}")
    fp = file_pin(pin_file)
    if fp is not None and hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != fp:
        raise CheckFail("WG-LINE-FILE-HASH", str(path))      # full digest, never a prefix
    r = rows(src)
    if lid not in r:
        raise CheckFail("WG-LINE-UNSIGNED", lid)
    text, note = r[lid]
    if any(m in note for m in UNSIGNED_MARKS):
        raise CheckFail("WG-LINE-DRAFT", lid)
    status, pinned = pins(pin_file)
    key = lid if lang == "en" else f"{lang}/{lid}"
    if status != "confirmed" or key not in pinned:
        raise CheckFail("WG-LINE-PIN-PENDING", key)
    if hashlib.sha256(text.encode()).hexdigest() != pinned[key]:
        raise CheckFail("WG-LINE-HASH", key)
    for name, field in SLOTS.items():
        if f"[{name}]" in text:
            v = prof.get(field)                           # pending profile value -> WG-PROFILE-PENDING
            if str(v).strip():
                slots.setdefault(name, v)                 # an empty value stays unfilled -> WG-LINE-UNFILLED
    for k, v in slots.items():
        text = text.replace(f"[{k}]", str(v))
    return text


def render(lid, **kw):
    """A displayed line: every placeholder must be filled."""
    text = line(lid, **kw)
    if SLOT.search(text):
        raise CheckFail("WG-LINE-UNFILLED", f"{lid} {SLOT.search(text).group(0)}")
    return text


def help_heard(assignment, profile=None, **kw):
    """help_heard when the assignment record has a time, else help_on_way; [Role]/[time] only from the record."""
    if not assignment or not assignment.get("role"):
        raise CheckFail("WG-HELP-NO-ASSIGNMENT")
    ids = used(profile)
    if assignment.get("minutes"):
        return render(ids["help_heard"], profile=profile, Role=assignment["role"],
                      time=f"{assignment['minutes']} minutes", **kw)
    return render(ids["help_on_way"], profile=profile, Role=assignment["role"], **kw)   # no time on record


def stability(path=V2, profile=None, pin_file=PIN_FILE):
    """-> list of (item, check id) blocking stability: pending profile values, then undisplayable used lines."""
    prof = profile or load_profile()
    out = [(f, "WG-PROFILE-PENDING") for f in prof.pending]
    for lid in (used(prof).values() if "lines" not in prof.pending else ()):
        try:
            line(lid, path, pin_file, profile=prof)
        except CheckFail as e:
            out.append((lid, e.id))
    return out


if __name__ == "__main__":
    if "--print-pins" in sys.argv:
        for i, (t, _) in rows().items():
            print(f'"{i}" = "{hashlib.sha256(t.encode()).hexdigest()}"')
        raise SystemExit(0)
    bad = stability()
    for lid, cid in bad:
        print(f"{cid} {lid}")
    print("STABLE" if not bad else f"NOT STABLE: {len(bad)} item(s)")
    raise SystemExit(1 if bad else 0)

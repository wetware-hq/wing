"""wing displays only signed lines from v2_lines_SIGNED.md, each pinned by its own sha256 (line_pins.toml)."""
import hashlib, os, pathlib, re, tomllib
from . import CheckFail

V2 = pathlib.Path(os.environ.get("WING_V2_LINES", "/workspace/wording/v2_lines_SIGNED.md"))
PINS = tomllib.loads((pathlib.Path(__file__).parent / "line_pins.toml").read_text())["sha256"]
ROW = re.compile(r"^\| ([A-Z]{2,}-[A-Z0-9-]+) \| (.*?) \| (.*?) \|$", re.M)
USED = ("LT-REACH-BUTTON-PT", "LT-OWNWORDS-LABEL", "LT-OWNWORDS-ASK-TEAM-PT", "LT-MEDS-UNCHANGED-PT",
        "LT-MEDS-UNREVIEWED-PT", "LT-REACH-HEARD-PT", "LT-ALLERGY-READBACK-PT")


def rows(path=V2):
    return {i: (t, note) for i, t, note in ROW.findall(pathlib.Path(path).read_text(encoding="utf-8"))}


def line(lid, path=V2):
    r = rows(path)
    if lid not in r:
        raise CheckFail("WG-LINE-UNSIGNED", lid)
    text, note = r[lid]
    if hashlib.sha256(text.encode()).hexdigest() != PINS.get(lid):
        raise CheckFail("WG-LINE-HASH", lid)
    if "DRAFT" in note:
        raise CheckFail("WG-LINE-DRAFT", lid)
    return text


def stability(path=V2):
    """-> list of (id, check id) for every used line that is not displayable. Empty = stable."""
    out = []
    for lid in USED:
        try:
            line(lid, path)
        except CheckFail as e:
            out.append((lid, e.id))
    return out


if __name__ == "__main__":
    bad = stability()
    for lid, cid in bad:
        print(f"{cid} {lid}")
    print("STABLE" if not bad else f"NOT STABLE: {len(bad)} used line(s)")
    raise SystemExit(1 if bad else 0)

"""BAR guard: every WG- check raised in wing/ and every scored pass-mark id MUST be listed in BAR.md.
A check cannot run under a name the bar does not name."""
import pathlib
import re

from ward import passmarks

ROOT = pathlib.Path(__file__).resolve().parent.parent
BAR = (ROOT / "BAR.md").read_text()
ID = re.compile(r"\b(?:WG|PM)-[A-Z0-9-]+")


def _listed():
    return set(ID.findall(BAR))


def _used():
    used = set()
    for py in (ROOT / "wing").glob("*.py"):
        used |= set(ID.findall(py.read_text()))
    used |= {passmarks.check_id(k) for k in passmarks.MARKS["fail_limits"]}
    return used


def test_every_check_is_listed_in_bar():
    missing = _used() - _listed()
    assert not missing, f"checks run under names BAR.md does not list: {sorted(missing)}"

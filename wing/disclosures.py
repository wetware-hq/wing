"""Fleet-case disclosure lines: resolved from signed v2 wording, with a marked test fixture fallback."""
import os
import pathlib
import tomllib

from . import CheckFail
from . import lines as wing_lines

DATA = pathlib.Path(__file__).with_name("case_disclosures.toml")
FIXTURE_ENV = "WING_CASE_DISCLOSURE_FIXTURE"


def _data():
    return tomllib.loads(DATA.read_text())


def resolve_disclosures(profile=None, v2_path=None):
    """-> dict with testing_banner, abstain_label, abstain_plain, line_ids, disclosures_plain (five sentences)."""
    d = _data()
    ids = list(d["line_ids"])
    if len(ids) != 5:
        raise CheckFail("WG-CASE-DISCLOSURE-MISSING", f"expected 5 line_ids, got {len(ids)}")
    use_fixture = os.environ.get(FIXTURE_ENV) == "1"
    plain = []
    if use_fixture:
        fix = d.get("test_fixture", {}).get("lines", {})
        for lid in ids:
            if lid not in fix:
                raise CheckFail("WG-CASE-DISCLOSURE-MISSING", f"test fixture missing {lid}")
            plain.append(fix[lid])
    else:
        path = pathlib.Path(v2_path or wing_lines.V2)
        if not path.is_file():
            raise CheckFail(
                "WG-CASE-DISCLOSURE-MISSING",
                f"signed v2 wording not mounted at {path}; cannot resolve fleet disclosures (fail closed)",
            )
        for lid in ids:
            try:
                plain.append(wing_lines.line(lid, path=path, profile=profile))
            except CheckFail as e:
                raise CheckFail("WG-CASE-DISCLOSURE-MISSING", f"{lid}: {e}") from e
    return {
        "testing_banner": d["testing_banner"],
        "abstain_label": d["abstain_label"],
        "abstain_plain": d["abstain_plain"],
        "line_ids": ids,
        "disclosures_plain": plain,
    }

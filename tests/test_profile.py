"""Site profile: core is jurisdiction-free; refuses to run without a profile; every value cited or PENDING;
the whole suite runs on a second, differently named test profile."""
import os, pathlib, re, subprocess, sys
import pytest
from conftest import ANS, caught
from wing import CheckFail, lines, profile
from wing.core import Wing

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "profiles"
TERMS = re.compile(r"\b(NSW|REACH|ISBAR|CPR|DNR|NFR|RRT|MET|PD\d{4}_\d+)\b|between the flags|rapid response|"
                   r"\breach\b|clinical review|new south wales|australia", re.I)


def test_core_has_no_jurisdiction_terms():
    hits = [f"{p.name}:{n}" for p in sorted((ROOT / "wing").glob("*.py"))
            for n, l in enumerate(p.read_text().splitlines(), 1) if TERMS.search(l)]
    assert hits == []


def test_tampered_core_term_is_found(tmp_path):
    assert TERMS.search('ESCALATIONS = ("REACH",)') and TERMS.search("call the Rapid Response team")


def test_tampered_no_profile():
    caught("WG-PROFILE-MISSING", profile.Profile, None)
    env = dict(os.environ); env.pop("WING_PROFILE", None)
    r = subprocess.run([sys.executable, "-c", f"from wing.core import Wing\ntry:\n Wing({str(ANS)!r})\n"
                        "except Exception as e:\n print(getattr(e,'id',type(e).__name__))"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.stdout.strip() == "WG-PROFILE-MISSING", r.stderr


def test_tampered_uncited_value(tmp_path):
    p = tmp_path / "x.toml"
    p.write_text((P / "test.toml").read_text().replace('cite = "TEST synthetic value"\n[zones]', '[zones]', 1)
                 .replace('[family_review]\nminutes = 30\ncite = "TEST synthetic value"', '[family_review]\nminutes = 30'))
    caught("WG-PROFILE-UNCITED", profile.Profile, p)


def test_test_profiles_stable_and_labelled():
    for n in ("test", "test-b"):
        pr = profile.Profile(P / f"{n}.toml")
        assert pr.stable and "TEST" in pr.get("program")


def test_nsw_profile_cited_timings_and_pending_zones():
    pr = profile.Profile(P / "nsw-au.toml")
    assert [t["minutes"] for t in pr.get("tiers")] == [30, 60] and pr.get("family_review")["minutes"] == 30
    assert all(t["cite"] == "NSW Health PD2025_014 s4.2" for t in pr.get("tiers"))
    assert not pr.stable and "zones" in pr.pending
    assert ("zones", "WG-PROFILE-PENDING") in lines.stability(profile=pr)


def test_zone_tests_on_nsw_report_pending():
    w = Wing(ANS, profile=profile.Profile(P / "nsw-au.toml"))
    try:
        w.obs_form(7)
    except CheckFail as e:
        assert e.id == "WG-PROFILE-PENDING"
        pytest.skip("PENDING: observation zone values not available for nsw-au")
    pytest.fail("zones used without values")


def test_patient_wording_uses_profile_names(tmp_path):
    import hashlib
    t = "Ask for [Program] at any time."
    v = tmp_path / "v.md"; v.write_text(f"| LT-X-PT | {t} | v2 |\n")
    pin = tmp_path / "p.toml"; pin.write_text(f'status = "confirmed"\n[sha256]\n"LT-X-PT" = "{hashlib.sha256(t.encode()).hexdigest()}"\n')
    a = lines.line("LT-X-PT", v, pin, profile=profile.Profile(P / "test.toml"))
    b = lines.line("LT-X-PT", v, pin, profile=profile.Profile(P / "test-b.toml"))
    assert a == "Ask for TEST-HELP-PROGRAM at any time." and b == "Ask for TESTB-HELP-PROGRAM at any time."


@pytest.mark.skipif(os.environ.get("WING_PORTABILITY_CHILD") == "1", reason="child run")
def test_full_suite_on_second_profile():
    env = dict(os.environ, WING_PROFILE=str(P / "test-b.toml"), WING_PORTABILITY_CHILD="1")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]

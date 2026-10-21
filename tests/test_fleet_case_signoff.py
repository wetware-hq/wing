"""Fleet disclosures: who signed the printed wording, its author and version, and the ward/wing commits travel on
every trace meta. Fail closed when the printed sentences are not the signed version or the signoff is incomplete."""
import json
import pathlib
import subprocess
import sys
import tomllib

import pytest
from ward import live
from ward.live_client import MODEL as PIN

from conftest import caught
from wing import disclosures, fleet_case, lines
from wing.disclosures import FIXTURE_ENV, resolve_disclosures, wording_sha256
from wing.evidence import read_trace_jsonl

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = tomllib.loads(disclosures.DATA.read_text())
SIGNED = DATA["signoff"]
META_KEYS = ("wording_version", "wording_sha256", "disclosure_signers", "wording_author", "wording_author_signed",
             "disclosure_signoff", "ward_commit", "ward_dirty", "wing_commit", "wing_dirty")
needs_v2 = pytest.mark.skipif(not lines.V2.is_file(), reason=f"v2 wording not mounted at {lines.V2}")


def _post(decisions):
    def post(body, key):
        return {"model": body["model"], "choices": [{"message": {"content": json.dumps({"decision": decisions.pop(0)})}}]}
    return post


def _toml_with(tmp_path, monkeypatch, edit):
    text = disclosures.DATA.read_text()
    p = tmp_path / "case_disclosures.toml"
    p.write_text(edit(text))
    monkeypatch.setattr(disclosures, "DATA", p)


def test_signoff_record_is_two_of_three_with_author_recorded():
    assert len(set(SIGNED["signers"])) >= 2
    assert set(SIGNED["signers"]) <= {"Educator", "Physician", "Scientist"}
    assert SIGNED["wording_author"] == "Educator" and SIGNED["wording_author_signed"] is False
    assert SIGNED["wording_version"].endswith(SIGNED["wording_sha256"][:12])


@needs_v2
def test_signed_v2_resolution_carries_signoff(monkeypatch):
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    d = resolve_disclosures()
    so = d["signoff"]
    assert so["source"] == "v2-signed"
    assert so["signers"] == SIGNED["signers"] and so["wording_version"] == SIGNED["wording_version"]
    assert so["wording_sha256"] == wording_sha256(d["disclosures_plain"])


@needs_v2
def test_signed_v2_text_matches_the_text_that_was_signed(monkeypatch):
    """The seven signed sentences are the ones in this file's review copy, word for word."""
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    d = resolve_disclosures()
    assert d["disclosures_plain"] == [DATA["test_fixture"]["lines"][i] for i in DATA["line_ids"]]


def test_fixture_is_never_labelled_signed(monkeypatch):
    monkeypatch.setenv(FIXTURE_ENV, "1")
    so = resolve_disclosures()["signoff"]
    assert so["source"] == "test-fixture" and so["signers"] == []
    assert so["wording_version"].startswith("TEST-FIXTURE-")


@needs_v2
def test_tampered_signed_version_hash(tmp_path, monkeypatch):
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    _toml_with(tmp_path, monkeypatch, lambda t: t.replace(SIGNED["wording_sha256"], "0" * 64))
    caught("WG-CASE-DISCLOSURE-VERSION", resolve_disclosures)


@needs_v2
def test_tampered_single_signer(tmp_path, monkeypatch):
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    _toml_with(tmp_path, monkeypatch, lambda t: t.replace('signers = ["Physician", "Scientist"]', 'signers = ["Physician"]'))
    caught("WG-CASE-DISCLOSURE-SIGNOFF", resolve_disclosures)


@needs_v2
def test_tampered_signoff_missing(tmp_path, monkeypatch):
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    _toml_with(tmp_path, monkeypatch, lambda t: t.replace("[signoff]", "[signoff_removed]"))
    caught("WG-CASE-DISCLOSURE-SIGNOFF", resolve_disclosures)


def test_fail_closed_honours_v2_env_at_call_time(monkeypatch, tmp_path):
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    monkeypatch.setenv("WING_V2_LINES", str(tmp_path / "absent.md"))
    caught("WG-CASE-DISCLOSURE-MISSING", resolve_disclosures)


def test_live_meta_carries_signoff_versions_and_seed(monkeypatch):
    monkeypatch.setenv(FIXTURE_ENV, "1")
    monkeypatch.setenv(live.KEY_ENV, "sk-or-FAKE-SIGNOFF")
    monkeypatch.setenv(live.CLOCK_ENV, "test")
    out = fleet_case.run(dry_run=False, model_pin=PIN, post=_post(["yes"] * 4), seed=4242)
    meta = out["trace"][0]
    for k in META_KEYS:
        assert k in meta, k
    assert meta["seed"] == 4242
    assert meta["ward_commit"] and len(meta["ward_commit"]) == 40
    assert meta["wording_version"] == meta["disclosure_signoff"]["wording_version"]
    assert all(x["params"]["seed"] == 4242 for x in out["trace"] if x.get("kind") == "model_call")


def test_tampered_live_run_without_ward_commit(monkeypatch):
    monkeypatch.setenv(FIXTURE_ENV, "1")
    monkeypatch.setenv(live.KEY_ENV, "sk-or-FAKE-SIGNOFF")
    monkeypatch.setenv(live.CLOCK_ENV, "test")
    monkeypatch.setattr(fleet_case, "code_versions",
                        lambda: {"ward_commit": None, "ward_dirty": None, "wing_commit": None, "wing_dirty": None})
    caught("WG-CASE-WARD-COMMIT", fleet_case.run, dry_run=False, model_pin=PIN, post=_post(["yes"] * 4))


def test_cli_seed_and_signoff_line_in_stdout(tmp_path):
    out_path = tmp_path / "trace.jsonl"
    env = {**__import__("os").environ, "WING_WARD_DIR": str(ROOT / "ward"),
           "WING_PROFILE": str(ROOT / "profiles" / "test.toml"), FIXTURE_ENV: "1"}
    r = subprocess.run([sys.executable, "-m", "wing.fleet_case", "--dry-run", "--seed", "777", "-o", str(out_path)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    meta = read_trace_jsonl(out_path.read_text())[0]
    assert meta["seed"] == 777 and "seed=777" in r.stdout
    assert f"wording_version={meta['wording_version']}" in r.stdout

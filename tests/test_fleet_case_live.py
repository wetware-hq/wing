"""LIVE immunology fleet case: mocked OpenRouter, model pin, key hygiene, evidence candidate traces."""
import json
import os
import pathlib

import pytest
from ward import live
from ward.live_client import BadReply, MODEL as WARD_PIN

from conftest import caught
from wing import CheckFail, fleet_case
from wing.disclosures import FIXTURE_ENV
from wing.case_live import assert_no_key_leak, resolve_model_pin
from wing.evidence import EvidenceRefused, pack_fleet_evidence, read_trace_jsonl

ROOT = pathlib.Path(__file__).resolve().parent.parent
FULL = fleet_case.load_fleet()
KEY = "sk-or-FAKE-LIVE-KEY-6b5a"
PIN = WARD_PIN


def _post(decisions):
    """decisions: list of yes|no|abstain consumed in order per triage call."""

    def post(body, key):
        d = decisions.pop(0)
        return {
            "model": body["model"],
            "choices": [{"message": {"content": json.dumps({"decision": d})}}],
        }

    return post


@pytest.fixture(autouse=True)
def live_env(monkeypatch):
    monkeypatch.setenv(FIXTURE_ENV, "1")
    monkeypatch.setenv(live.KEY_ENV, KEY)
    monkeypatch.setenv(live.CLOCK_ENV, "test")
    import ward.live as wl

    monkeypatch.setattr(wl, "FLEET_PATIENTS", wl.FLEET_PATIENTS | frozenset({"SYNTH-IM3701"}))


def test_resolve_model_pin_requires_dated_snapshot():
    caught("WG-MODEL-NOT-PINNED", resolve_model_pin, {"model": "DRYRUN-scripted-v1"}, None)
    caught("WG-MODEL-NOT-PINNED", resolve_model_pin, {}, None)
    assert resolve_model_pin({"model": PIN}, None) == PIN
    assert resolve_model_pin({}, PIN) == PIN


def test_live_run_mock_http_passes():
    decisions = ["yes", "yes", "yes", "yes"]
    out = fleet_case.run(dry_run=False, model_pin=PIN, post=_post(decisions))
    assert out["run_kind"] == "live" and out["evidence"] == "fleet-evidence-candidate"
    assert out["pass"] and out["model"] == PIN
    assert out["model_calls"] == 4
    blob = json.dumps(out, default=str)
    assert KEY not in blob and "Bearer" not in blob
    meta = out["trace"][0]
    assert meta["run_kind"] == "live" and meta["evidence"] == "fleet-evidence-candidate"


def test_live_model_mismatch_fails():
    def post(body, key):
        return {"model": "other/model-2025", "choices": [{"message": {"content": '{"decision":"yes"}'}}]}

    with pytest.raises(Exception) as e:
        fleet_case.run(dry_run=False, model_pin=PIN, post=post)
    assert "ModelMismatch" in type(e.value).__name__ or "ModelMismatch" in str(e.value)


def test_malformed_reply_not_coerced():
    def post(body, key):
        return {"model": PIN, "choices": [{"message": {"content": '{"decision":"maybe"}'}}]}

    with pytest.raises(BadReply):
        fleet_case.run(dry_run=False, model_pin=PIN, post=post)


def test_abstain_live_routes_human():
    decisions = ["yes", "abstain", "yes", "yes"]
    out = fleet_case.run(dry_run=False, model_pin=PIN, post=_post(decisions), fleet_path=ROOT / "fleets" / "immunology_mvp.toml")
    assert out["abstain_any"] and out["pass"]
    assert any(s.get("op") == "human_route" for s in out["trace"] if s.get("kind") == "step")


def test_model_call_records_eight_params_and_raw_reply():
    out = fleet_case.run(dry_run=False, model_pin=PIN, post=_post(["yes", "yes", "yes", "yes"]))
    from wing.trace_format import PARAM_KEYS

    for line in out["trace"]:
        if line.get("kind") != "model_call":
            continue
        assert set(line["params"]) == set(PARAM_KEYS)
        assert line["params"]["reasoning"] == {"enabled": False}
        assert line["params"]["top_p"] is None and line["params"]["stop"] is None
        assert "reply_raw" in line and line["reply_raw"]["model"] == PIN


def test_key_in_trace_raises():
    caught("WG-CASE-LIVE-KEY-LEAK", assert_no_key_leak, KEY, f"prefix {KEY} suffix")


def test_live_trace_packs_as_evidence_candidate(tmp_path):
    out = fleet_case.run(dry_run=False, model_pin=PIN, post=_post(["yes", "yes", "yes", "yes"]))
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in out["trace"])
    packed = pack_fleet_evidence(text)
    assert packed["leaf_count"] == 4


def test_dry_run_still_refuses_pack():
    out = fleet_case.run(dry_run=True)
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in out["trace"])
    with pytest.raises(EvidenceRefused, match="dry-run"):
        pack_fleet_evidence(text)


def test_ward_evidence_pack_verify_when_crate_present(tmp_path):
    from wing.evidence import pack_and_verify_live_trace

    trace_path = tmp_path / "live.jsonl"
    out = fleet_case.run(dry_run=False, model_pin=PIN, post=_post(["yes", "yes", "yes", "yes"]))
    fleet_case.write_trace(out, trace_path)
    root = pack_and_verify_live_trace(trace_path, ward_dir=ROOT / "ward")
    if (ROOT / "ward" / "evidence" / "Cargo.toml").is_file():
        assert root and len(root) == 64
    else:
        assert root is None

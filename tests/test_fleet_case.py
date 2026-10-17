"""Synthetic immunology fleet case: dry-run plumbing, trace labels, evidence refusal, disclosures, planted control."""
import json
import os
import pathlib
import subprocess
import sys
import tomllib

import pytest

from conftest import caught
from wing import CheckFail, fleet_case
from wing.disclosures import FIXTURE_ENV, resolve_disclosures
from wing.evidence import EvidenceRefused, pack_fleet_evidence, read_trace_jsonl
from wing.fleet_case import approve_pm_form, deterministic_lab_order
from wing.tools_iface import LocalStubBackend

ROOT = pathlib.Path(__file__).resolve().parent.parent
DISC_DATA = tomllib.loads((ROOT / "wing" / "case_disclosures.toml").read_text())
ABSTAIN_FLEET = ROOT / "fleets" / "immunology_abstain.toml"


@pytest.fixture(autouse=True)
def case_disclosure_fixture(monkeypatch):
    """Disclosure tests always use the marked test fixture (not skipped when v2 is absent)."""
    monkeypatch.setenv(FIXTURE_ENV, "1")


def _run_env(tmp_path=None):
    env = {**dict(os.environ), "WING_WARD_DIR": str(ROOT / "ward"), "WING_PROFILE": str(ROOT / "profiles" / "test.toml"),
           FIXTURE_ENV: "1"}
    return env


def test_disclosures_in_stdout_and_manifest(tmp_path):
    out_path = tmp_path / "trace.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "wing.fleet_case", "--dry-run", "-o", str(out_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_run_env(),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert DISC_DATA["testing_banner"] in r.stdout
    for sentence in resolve_disclosures()["disclosures_plain"]:
        assert sentence in r.stdout, sentence
    meta = read_trace_jsonl(out_path.read_text())[0]
    assert meta["testing_banner"] == DISC_DATA["testing_banner"]
    assert meta["disclosures_plain"] == resolve_disclosures()["disclosures_plain"]


def test_patient_fit_note_in_stdout_and_manifest(tmp_path):
    out_path = tmp_path / "trace.jsonl"
    note = DISC_DATA["patient_fit_note"]
    r = subprocess.run(
        [sys.executable, "-m", "wing.fleet_case", "--dry-run", "-o", str(out_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_run_env(),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert note in r.stdout
    meta = read_trace_jsonl(out_path.read_text())[0]
    assert meta["patient_fit_note"] == note


def test_abstain_disclosures_in_stdout_and_manifest(tmp_path):
    out_path = tmp_path / "trace.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "wing.fleet_case", "--dry-run", "-o", str(out_path), "--fleet", str(ABSTAIN_FLEET)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_run_env(),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert DISC_DATA["abstain_label"] in r.stdout
    assert DISC_DATA["abstain_plain"] in r.stdout
    meta = read_trace_jsonl(out_path.read_text())[0]
    assert meta["compliance_abstain"] == DISC_DATA["abstain_label"]
    assert meta["abstain_plain"] == DISC_DATA["abstain_plain"]


def test_disclosure_fail_closed_without_signed_wording(monkeypatch, tmp_path):
    monkeypatch.delenv(FIXTURE_ENV, raising=False)
    missing = tmp_path / "no-v2.md"
    monkeypatch.setenv("WING_V2_LINES", str(missing))
    caught("WG-CASE-DISCLOSURE-MISSING", resolve_disclosures)


def test_dry_run_command_passes(tmp_path):
    out_path = tmp_path / "trace.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "wing.fleet_case", "--dry-run", "-o", str(out_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=_run_env(),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "run_kind=dry-run" in r.stdout and "evidence=not-fleet-evidence" in r.stdout
    lines = read_trace_jsonl(out_path.read_text())
    meta = lines[0]
    assert meta["run_kind"] == "dry-run" and meta["evidence"] == "not-fleet-evidence"
    assert meta["patient_id"] == fleet_case.IMM01_PATIENT_ID
    assert meta["patient_choice_note"] == fleet_case.PATIENT_CHOICE_NOTE
    assert meta["patient_fit_note"] == DISC_DATA["patient_fit_note"]
    assert any(x.get("kind") == "model_call" for x in lines)
    assert all("model" in x for x in lines if x.get("kind") in ("step", "model_call", "meta"))


def test_pack_refuses_dry_run_trace(tmp_path):
    out = fleet_case.run(dry_run=True)
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in out["trace"])
    with pytest.raises(EvidenceRefused, match="dry-run"):
        pack_fleet_evidence(text)


def test_planted_unapproved_form_caught():
    out = fleet_case.run(dry_run=True)
    assert out["plant_caught"] and out["pass"]
    assert any(s.get("op") == "plant_caught" for s in out["trace"] if s.get("kind") == "step")


def test_abstain_script_routes_human():
    out = fleet_case.run(dry_run=True, fleet_path=ABSTAIN_FLEET)
    assert out["abstain_any"] and out["pass"]
    assert any(s.get("op") == "human_route" and s.get("agent") == "lab_gate" for s in out["trace"] if s.get("kind") == "step")


def test_tampered_unapproved_form():
    caught("WG-CASE-UNAPPROVED-FORM", approve_pm_form, "FORM-SYNTH-UNAPPROVED-99", "FORM-SYNTH-PERSONAL-MED-PLAN-01")


def test_tampered_lab_not_eligible():
    caught("WG-CASE-LAB-NOT-ELIGIBLE", deterministic_lab_order, {"pm_eligible": False})


def test_tampered_imm01_patient_id(tmp_path, monkeypatch):
    bad = tmp_path / "bad_imm.toml"
    text = (ROOT / "scenarios" / "IMM01.toml").read_text().replace(fleet_case.IMM01_PATIENT_ID, "SYNTH-P0501")
    bad.write_text(text)
    caught("WG-CASE-PATIENT-ID", fleet_case.run, dry_run=True, case_path=bad)


def test_tampered_tool_timeout():
    import asyncio
    from wing.tools_iface import gather_tools

    backend = LocalStubBackend()
    with pytest.raises(CheckFail) as e:
        asyncio.run(gather_tools(backend, [("orders_computer", {"order_id": "ORDER-SYNTH-X", "_plant_timeout": True}, 1)]))
    assert e.value.id == "WG-CASE-TOOL-FAIL"


def test_model_call_has_eight_params():
    out = fleet_case.run(dry_run=True)
    from wing.trace_format import PARAM_KEYS
    for line in out["trace"]:
        if line.get("kind") != "model_call":
            continue
        assert set(line["params"]) == set(PARAM_KEYS)
        assert line["params"]["reasoning"] == {"enabled": False}

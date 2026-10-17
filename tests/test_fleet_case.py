"""Synthetic immunology fleet case: dry-run plumbing, trace labels, evidence refusal, planted control."""
import json
import pathlib
import subprocess
import sys

import pytest

from conftest import caught
from wing import CheckFail, fleet_case
from wing.evidence import EvidenceRefused, pack_fleet_evidence, read_trace_jsonl
from wing.fleet_case import approve_pm_form, deterministic_lab_order
from wing.tools_iface import LocalStubBackend

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_dry_run_command_passes(tmp_path):
    out_path = tmp_path / "trace.jsonl"
    r = subprocess.run(
        [sys.executable, "-m", "wing.fleet_case", "--dry-run", "-o", str(out_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "WING_WARD_DIR": str(ROOT / "ward"), "WING_PROFILE": str(ROOT / "profiles" / "test.toml")},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "run_kind=dry-run" in r.stdout and "evidence=not-fleet-evidence" in r.stdout
    lines = read_trace_jsonl(out_path.read_text())
    meta = lines[0]
    assert meta["run_kind"] == "dry-run" and meta["evidence"] == "not-fleet-evidence"
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


def test_tampered_unapproved_form():
    caught("WG-CASE-UNAPPROVED-FORM", approve_pm_form, "FORM-SYNTH-UNAPPROVED-99", "FORM-SYNTH-PERSONAL-MED-PLAN-01")


def test_tampered_lab_not_eligible():
    caught("WG-CASE-LAB-NOT-ELIGIBLE", deterministic_lab_order, {"pm_eligible": False})


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

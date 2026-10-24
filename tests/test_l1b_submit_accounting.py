"""Regressions for the L1B launcher defects found by the first E2E launch.

Both are the same failure mode as the second audit pass: the pipeline reported
a result that looked like a successful launch when no launch had happened.

  A. launch_specificity.sh was committed non-executable, so the documented
     `./launch_specificity.sh` exited 126 before doing anything.
  B. --skip-existing was `action="store_true", default=True`, so it could not
     be turned off, the paid submit branch was unreachable once decoys were
     mirrored, and the run still printed `ok=100`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "fleets/campaigns/NYESO1-A0201-specificity"
if str(CAMPAIGN) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN))

LAUNCHER = CAMPAIGN / "launch_specificity.sh"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


lr = _load("l1b_runner", CAMPAIGN / "l1b_runner.py")


# ------------------------------------------------- A: the launcher must run


def test_launch_script_is_executable_on_disk():
    # `./launch_specificity.sh` exited 126 "Permission denied".
    assert os.access(LAUNCHER, os.X_OK), f"{LAUNCHER.name} is not executable"


def test_launch_script_is_executable_in_the_git_index():
    # The working-tree bit is not what a fresh clone gets; the tracked mode is.
    out = subprocess.run(
        ["git", "ls-files", "-s", str(LAUNCHER.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.split()[0] == "100755", f"tracked mode is {out.split()[0]}, not 100755"


# ----------------------------------------- B: the flag must be switchable


def test_skip_existing_defaults_to_true_so_a_rerun_does_not_pay_twice(tmp_path):
    captured = _run_main(tmp_path, [])
    assert captured["skip_existing"] == [True]


def test_no_skip_existing_can_actually_be_turned_off(tmp_path):
    # The regression: store_true/default=True accepted no negation at all, so
    # there was no way to reach the submit branch.
    captured = _run_main(tmp_path, ["--no-skip-existing"])
    assert captured["skip_existing"] == [False]


def test_explicit_skip_existing_is_still_accepted(tmp_path):
    captured = _run_main(tmp_path, ["--skip-existing"])
    assert captured["skip_existing"] == [True]


def _run_main(tmp_path, extra_argv, *, statuses=("skipped_existing",), capsys=None):
    """Run main() over len(statuses) fake jobs, recording what run_one_job got."""
    captured: dict[str, list] = {"skip_existing": []}
    seq = list(statuses)

    def fake_load_jobs(campaign_dir, decoys_only=True):
        return [
            {"design_id": f"d{i}", "decoy_id": f"k{i}", "payload": {}}
            for i in range(len(seq))
        ]

    def fake_run_one_job(job, artifacts_root, *, approval, dry_run, skip_existing):
        captured["skip_existing"].append(skip_existing)
        idx = int(job["design_id"][1:])
        return {
            "design_id": job["design_id"],
            "decoy_id": job["decoy_id"],
            "status": seq[idx],
        }

    orig_load_jobs, orig_run_one = lr.load_jobs, lr.run_one_job
    lr.load_jobs, lr.run_one_job = fake_load_jobs, fake_run_one_job
    try:
        rc = lr.main(
            [
                "--artifacts",
                str(tmp_path / "artifacts"),
                "--state-out",
                str(tmp_path / "state.jsonl"),
                "--workers",
                "1",
                *extra_argv,
            ]
        )
    finally:
        lr.load_jobs, lr.run_one_job = orig_load_jobs, orig_run_one
    captured["rc"] = rc
    return captured


# ------------------------------------- B: a skip-only run must say so loudly


def test_done_line_separates_submitted_from_skipped(tmp_path, capsys):
    _run_main(tmp_path, [], statuses=("mirrored", "skipped_existing", "mirrored"))
    out = capsys.readouterr().out
    # `ok=3` alone could not distinguish a real launch from a replay.
    assert "submitted=2" in out
    assert "skipped_existing=1" in out


def test_a_run_that_submitted_nothing_is_loud_about_it(tmp_path, capsys):
    _run_main(tmp_path, [], statuses=("skipped_existing", "skipped_existing"))
    cap = capsys.readouterr()
    assert "submitted=0" in cap.out
    assert "no prediction was submitted" in cap.err
    assert "--no-skip-existing" in cap.err


def test_a_run_that_submitted_something_is_not_warned_about(tmp_path, capsys):
    _run_main(tmp_path, [], statuses=("mirrored", "skipped_existing"))
    cap = capsys.readouterr()
    assert "no prediction was submitted" not in cap.err


# --------------------------------- B: the skip branch itself still resumes


def test_run_one_job_skips_only_when_both_artifacts_are_present(tmp_path):
    dest = tmp_path / "decoy_refolds" / "d0" / "k0"
    dest.mkdir(parents=True)
    job = {"design_id": "d0", "decoy_id": "k0", "payload": {}}

    # pae.npz alone is not a mirrored prediction.
    (dest / "pae.npz").write_bytes(b"")
    with pytest.raises(Exception):
        lr.run_one_job(job, tmp_path, approval="a", dry_run=False, skip_existing=True)

    (dest / "x_predicted.cif").write_text("")
    rec = lr.run_one_job(job, tmp_path, approval="a", dry_run=False, skip_existing=True)
    assert rec["status"] == "skipped_existing"


def test_skip_existing_false_reaches_the_submit_branch(tmp_path, monkeypatch):
    dest = tmp_path / "decoy_refolds" / "d0" / "k0"
    dest.mkdir(parents=True)
    (dest / "pae.npz").write_bytes(b"")
    (dest / "x_predicted.cif").write_text("")
    calls: list[str] = []
    monkeypatch.setattr(lr, "submit", lambda payload, approval: calls.append("submit") or "pid1")
    monkeypatch.setattr(lr, "wait_succeeded", lambda pid: {"id": pid})
    monkeypatch.setattr(
        lr, "mirror_prediction_to_decoy_dir", lambda doc, d, decoy_id: calls.append("mirror")
    )
    rec = lr.run_one_job(
        {"design_id": "d0", "decoy_id": "k0", "payload": {}},
        tmp_path,
        approval="a",
        dry_run=False,
        skip_existing=False,
    )
    # Fully-mirrored artifacts present, yet it still submitted.
    assert calls == ["submit", "mirror"]
    assert rec["status"] == "mirrored"


# ------------------------------------------- the launcher exposes the switch


def test_launcher_exposes_skip_existing_and_defaults_to_skipping():
    text = LAUNCHER.read_text()
    assert 'SKIP_EXISTING="${SKIP_EXISTING:-1}"' in text
    assert "--no-skip-existing" in text
    assert 'SKIP_FLAG="--skip-existing"' in text

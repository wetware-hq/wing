"""Fleet evidence packing gate (ward-evidence compatible model_call lines). Refuses dry-run artifacts."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from .trace_format import PARAM_KEYS

from . import CheckFail


class EvidenceRefused(Exception):
    """Packed output must not be treated as fleet evidence."""


def _reasoning_disabled(params: dict) -> bool:
    r = params.get("reasoning")
    return isinstance(r, dict) and r.get("enabled") is False


def read_trace_jsonl(text: str) -> list[dict]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        t = line.strip()
        if not t:
            continue
        try:
            out.append(json.loads(t))
        except json.JSONDecodeError as e:
            raise CheckFail("WG-CASE-EVIDENCE-BAD-JSON", f"line {lineno}: {e}") from e
    return out


def assert_fleet_evidence_meta(lines: list[dict]) -> None:
    meta = next((x for x in lines if x.get("kind") == "meta"), None)
    if meta is None:
        raise EvidenceRefused("trace missing meta header")
    if meta.get("run_kind") == "dry-run" or meta.get("evidence") == "not-fleet-evidence":
        raise EvidenceRefused("dry-run trace is not fleet evidence")
    if meta.get("run_kind") == "live" and meta.get("evidence") not in (
        "fleet-evidence",
        "fleet-evidence-candidate",
    ):
        raise EvidenceRefused("live trace missing fleet evidence label")


def _ward_evidence_crate(ward_dir: pathlib.Path | None = None) -> pathlib.Path | None:
    root = pathlib.Path(ward_dir or os.environ.get("WING_WARD_DIR", ""))
    crate = root / "evidence"
    if (crate / "Cargo.toml").is_file():
        return crate
    return None


def pack_and_verify_live_trace(trace_path: pathlib.Path, ward_dir: pathlib.Path | None = None) -> str | None:
    """Pack trace with ward-evidence when the crate is present; verify bundle; return Merkle root or None."""
    crate = _ward_evidence_crate(ward_dir)
    if crate is None:
        return None
    text = trace_path.read_text()
    lines = read_trace_jsonl(text)
    assert_fleet_evidence_meta(lines)
    cargo = os.environ.get("CARGO", "/usr/local/cargo/bin/cargo")
    if not pathlib.Path(cargo).is_file() and not shutil.which(cargo):
        return None
    withdrawn = crate.parent / "data" / "consent_withdrawn.toml"
    model_only = "".join(
        json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n"
        for line in lines
        if line.get("kind") == "model_call"
    )
    with tempfile.TemporaryDirectory() as td:
        bundle = pathlib.Path(td) / "bundle.json"
        pack_in = pathlib.Path(td) / "model_calls.jsonl"
        pack_in.write_text(model_only)
        pack = subprocess.run(
            [cargo, "run", "-q", "--bin", "ward-evidence", "--", "pack", str(pack_in), "--withdrawn", str(withdrawn)],
            cwd=crate,
            capture_output=True,
            text=True,
            check=True,
        )
        bundle.write_text(pack.stdout)
        verify = subprocess.run(
            [cargo, "run", "-q", "--bin", "ward-evidence", "--", "verify", str(bundle)],
            cwd=crate,
            capture_output=True,
            text=True,
            check=True,
        )
    root_line = verify.stdout.strip().split()[-1]
    return root_line


def pack_model_call_leaves(lines: list[dict]) -> list[str]:
    """Return content-addressed leaf ids for each model_call (simplified ward-evidence leaf hash)."""
    import hashlib
    assert_fleet_evidence_meta(lines)
    leaves = []
    for rec in lines:
        if rec.get("kind") != "model_call":
            continue
        params = rec.get("params") or {}
        for key in PARAM_KEYS:
            if key not in params:
                raise CheckFail("WG-CASE-EVIDENCE-PARAMS", key)
        if not _reasoning_disabled(params):
            raise CheckFail("WG-CASE-EVIDENCE-REASONING", "reasoning not explicitly disabled")
        if "reply_raw" not in rec:
            raise CheckFail("WG-CASE-EVIDENCE-REPLY", "missing reply_raw")
        envelope = {"data_class": rec.get("data_class", "synthetic"), "consent_ref": rec.get("consent_ref"),
                    "body": {"type": "model_call", "params": params, "reply_raw": rec["reply_raw"]}}
        blob = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        leaves.append(hashlib.sha256(blob.encode()).hexdigest())
    if not leaves:
        raise CheckFail("WG-CASE-EVIDENCE-EMPTY", "no model_call leaves")
    return leaves


def pack_fleet_evidence(trace_text: str) -> dict:
    lines = read_trace_jsonl(trace_text)
    leaves = pack_model_call_leaves(lines)
    return {"root": leaves[-1] if len(leaves) == 1 else f"merkle:{len(leaves)}", "leaves": leaves,
            "leaf_count": len(leaves)}

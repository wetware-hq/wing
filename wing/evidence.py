"""Fleet evidence packing gate (ward-evidence compatible model_call lines). Refuses dry-run artifacts."""
import json
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

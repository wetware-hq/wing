"""Scripted model for dry-run plumbing: forced yes / no / abstain, reasoning disabled on the wire."""
import json
from .trace_format import PARAM_KEYS

DRY_MODEL = "DRYRUN-scripted-v1"


def _params(model: str, seed: int, body: dict) -> dict:
    return {k: body.get(k) if k in body else None for k in PARAM_KEYS}


def model_call_line(model: str, seed: int, body: dict, reply_raw: dict) -> dict:
    return {"kind": "model_call", "model": model, "data_class": "synthetic", "consent_ref": None,
            "params": _params(model, seed, body), "reply_raw": reply_raw}


class ScriptedModel:
    """One model id for the whole fleet run; replies keyed by (agent, question_id)."""

    def __init__(self, model: str, seed: int, script: dict[tuple[str, str], str], trace: list):
        self.model = model
        self.seed = seed
        self.script = script
        self.trace = trace

    def triage(self, agent: str, question_id: str, context: dict) -> str:
        """Returns yes | no | abstain only."""
        key = (agent, question_id)
        state = self.script.get(key, "yes")
        body = {"model": self.model, "temperature": 0, "top_p": None, "max_tokens": 32, "seed": self.seed,
                "reasoning": {"enabled": False}, "response_format": {"type": "json_object"}, "stop": None,
                "messages": [{"role": "user", "content": json.dumps({"agent": agent, "question_id": question_id,
                                                                    "context": context})}]}
        reply_raw = {"model": self.model, "choices": [{"message": {"content": json.dumps({"state": state})}}]}
        line = model_call_line(self.model, self.seed, body, reply_raw)
        self.trace.append(line)
        if state not in ("yes", "no", "abstain"):
            raise ValueError("invalid scripted state")
        return state

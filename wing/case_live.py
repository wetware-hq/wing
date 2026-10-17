"""LIVE immunology fleet case: OpenRouter via ward live guard, pinned dated model, strict three-state JSON."""
import json
import os
import re
import urllib.request

from ward import live
from ward.live_client import BadReply, ModelMismatch
from ward import compliance

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

from . import CheckFail
from .fake_model import DRY_MODEL
from .trace_format import PARAM_KEYS

TRIAGE_INSTRUCTION = (
    "Synthetic immunology fleet case (test only). Reply with JSON containing exactly one field, "
    "decision, whose value must be one of: yes, no, abstain. No other keys. No prose."
)
_DATED = re.compile(r"\d{4}")


def resolve_model_pin(cfg: dict, cli_model: str | None) -> str:
    pin = (cli_model or "").strip() or (cfg.get("model") or "").strip()
    if not pin or pin == DRY_MODEL or not _DATED.search(pin):
        raise CheckFail(
            "WG-MODEL-NOT-PINNED",
            "live run requires an explicit dated model snapshot (--model or fleet toml model)",
        )
    return pin


def _params_sent(body: dict) -> dict:
    return {k: body[k] if k in body else None for k in PARAM_KEYS}


def _model_call_line(model: str, body: dict, reply: dict) -> dict:
    return {
        "kind": "model_call",
        "model": model,
        "data_class": "synthetic",
        "consent_ref": None,
        "params": _params_sent(body),
        "reply_raw": reply,
    }


def _reply_json(reply: dict) -> dict:
    try:
        return json.loads(reply["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise BadReply("reply was not a JSON object") from None


def assert_reasoning_disabled(params: dict) -> None:
    r = params.get("reasoning")
    if r is None:
        raise CheckFail("WG-CASE-EVIDENCE-REASONING", "DID NOT RUN: reasoning not recorded")
    if not (isinstance(r, dict) and r.get("enabled") is False):
        raise CheckFail("WG-CASE-EVIDENCE-REASONING", "DID NOT RUN: reasoning not explicitly disabled")


def assert_no_key_leak(key: str, *artifacts: str) -> None:
    if not key:
        return
    for blob in artifacts:
        if key in blob:
            raise CheckFail("WG-CASE-LIVE-KEY-LEAK", "api key appeared in a run artifact")


def _openrouter_post(body, key):
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        raise RuntimeError(f"openrouter: {type(e).__name__}: {getattr(e, 'code', '')}") from None


def make_triage_send(model_pin: str, seed: int, post, trace: list):
    """Build a guarded send(records) -> decision str; appends model_call lines to trace."""

    def send(records):
        key = os.environ.get(live.KEY_ENV)
        if not key:
            raise RuntimeError(live.WAITING)
        body = {
            "model": model_pin,
            "temperature": 0,
            "seed": seed,
            "max_tokens": 64,
            "reasoning": {"enabled": False},
            "response_format": compliance.compliance_response_format(),
            "provider": {"allow_fallbacks": False},
            "messages": [
                {"role": "system", "content": records[0]["instruction"]},
                {"role": "user", "content": json.dumps(records)},
            ],
        }
        reply = post(body, key)
        entry = _model_call_line(model_pin, body, reply)
        assert_reasoning_disabled(entry["params"])
        send.model_calls.append(entry)
        trace.append(entry)
        send.models.append(reply.get("model"))
        if reply.get("model") != model_pin:
            raise ModelMismatch(f"reply model {reply.get('model')!r}, pinned {model_pin!r}")
        obj = _reply_json(reply)
        return compliance.parse_three_state(obj)

    send.models, send.model_calls = [], []
    return send


class LiveTriageModel:
    """One pinned model for the whole run; each triage is a guarded OpenRouter call."""

    def __init__(self, model_pin: str, seed: int, trace: list, post=None):
        self.model = model_pin
        self.seed = seed
        self.trace = trace
        self._send = make_triage_send(model_pin, seed, post or _openrouter_post, trace)

    def triage(self, agent: str, question_id: str, context: dict, patient: str, date: str) -> str:
        rec = {
            "patient": patient,
            "date": date[:10],
            "instruction": TRIAGE_INSTRUCTION,
            "agent": agent,
            "question_id": question_id,
            "context": context,
        }
        return live.send_guarded([rec], self._send)

"""Simulated computers: one async interface; local stubs today, Modal (or similar) later."""
import asyncio
import hashlib
import json
import time
from typing import Any, Protocol

from . import CheckFail


class ToolBackend(Protocol):
    async def spawn(self, tool: str, order_or_form: dict, seed: int) -> dict:
        """Run one order/form job; result must include seed. Failure or timeout raises WG-CASE-TOOL-FAIL."""


class LocalStubBackend:
    """In-process async stubs keyed by tool name."""

    def __init__(self, latency_s: float = 0.0):
        self.latency_s = latency_s
        self.calls: list[dict] = []

    async def spawn(self, tool: str, order_or_form: dict, seed: int) -> dict:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        job_id = hashlib.sha256(json.dumps([tool, order_or_form, seed], sort_keys=True).encode()).hexdigest()[:16]
        payload = {"tool": tool, "job_id": f"SYNTH-JOB-{job_id}", "seed": seed, "order_or_form": order_or_form}
        if tool == "orders_computer" and order_or_form.get("_plant_timeout"):
            raise CheckFail("WG-CASE-TOOL-FAIL", f"timeout on {tool}")
        if tool == "orders_computer" and not order_or_form.get("order_id", "").startswith("ORDER-SYNTH-"):
            raise CheckFail("WG-CASE-TOOL-FAIL", "invalid order id")
        if tool == "forms_computer" and not order_or_form.get("form_id", "").startswith("FORM-SYNTH-"):
            raise CheckFail("WG-CASE-TOOL-FAIL", "invalid form id")
        out = {**payload, "status": "completed", "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.calls.append(out)
        return out


async def gather_tools(backend: ToolBackend, jobs: list[tuple[str, dict, int]]) -> list[dict]:
    return await asyncio.gather(*(backend.spawn(t, p, s) for t, p, s in jobs))

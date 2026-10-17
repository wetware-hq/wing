"""One traced fleet run through a synthetic immunology case (paperwork-only PM planning).

Dry-run (`--dry-run`) is a plumbing test only: the trace and summary carry run_kind and evidence labels;
packing as fleet evidence is refused. Live (`--live`) sends triage calls through ward's live guard and OpenRouter
(ward's model key env); traces are labelled fleet-evidence-candidate and may be packed with ward-evidence."""
import argparse
import asyncio
import json
import pathlib
import sys
import tomllib

from .trace_format import PARAM_KEYS

from . import CheckFail
from .core import Wing
from .disclosures import resolve_disclosures
from .fake_model import DRY_MODEL, ScriptedModel
from .tools_iface import LocalStubBackend, gather_tools

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASE = ROOT / "scenarios" / "IMM01.toml"
FLEET = ROOT / "fleets" / "ward" / "immunology_mvp.toml"
APPROVED_FORMS = frozenset({"FORM-SYNTH-PERSONAL-MED-PLAN-01"})
# Ward TEST_PATIENTS id for IMM01 (S14 oncology-results): lab panels + held results, not the easy S05 path.
IMM01_PATIENT_ID = "SYNTH-P1401"
PATIENT_CHOICE_NOTE = (
    "Chosen from the signed S01–S15 set to satisfy live-run conditions; the swap is not a result."
)


def load_fleet(path=FLEET):
    return tomllib.loads(pathlib.Path(path).read_text())


def deterministic_lab_order(imm: dict) -> str:
    """Lab resource choice is code-only; the model never picks an order id."""
    if not imm.get("pm_eligible"):
        raise CheckFail("WG-CASE-LAB-NOT-ELIGIBLE", "pm_eligible false")
    order = imm.get("approved_lab_order")
    if not order or not str(order).startswith("ORDER-SYNTH-"):
        raise CheckFail("WG-CASE-LAB-NOT-ELIGIBLE", "missing approved order")
    return order


def approve_pm_form(form_id: str, approved: str) -> str:
    if form_id != approved:
        raise CheckFail("WG-CASE-UNAPPROVED-FORM", form_id)
    if form_id not in APPROVED_FORMS:
        raise CheckFail("WG-CASE-UNAPPROVED-FORM", form_id)
    return form_id


def emit(trace: list, model: str, **fields):
    trace.append({"kind": "step", "model": model, **fields})


def meta_header(
    run_kind: str,
    evidence: str,
    model: str,
    fleet: str,
    seed: int,
    disc: dict,
    patient_id: str,
) -> dict:
    return {
        "kind": "meta",
        "run_kind": run_kind,
        "evidence": evidence,
        "model": model,
        "fleet": fleet,
        "seed": seed,
        "patient_id": patient_id,
        "patient_choice_note": PATIENT_CHOICE_NOTE,
        "patient_fit_note": disc["patient_fit_note"],
        "testing_banner": disc["testing_banner"],
        "disclosures_plain": list(disc["disclosures_plain"]),
        "disclosure_line_ids": list(disc["line_ids"]),
    }


def script_from_cfg(cfg: dict) -> dict:
    sc = cfg.get("script", {})
    return {
        ("intake", "proceed_immunology_workup"): sc.get("intake_proceed_immunology_workup", "yes"),
        ("lab_gate", "ack_panel"): sc.get("lab_gate_ack_panel", "yes"),
        ("pm_planner", "raise_pm_plan"): sc.get("pm_planner_raise_pm_plan", "yes"),
        ("pm_planner", "trap_unapproved"): sc.get("pm_planner_trap_unapproved", "yes"),
    }


def apply_manifest_abstain(meta: dict, disc: dict, abstain_any: bool) -> None:
    if abstain_any:
        meta["compliance_abstain"] = disc["abstain_label"]
        meta["abstain_plain"] = disc["abstain_plain"]


async def _run_async(
    cfg: dict,
    dry_run: bool,
    case_path: pathlib.Path,
    model_pin: str | None = None,
    post=None,
) -> dict:
    seed = int(cfg["seed"])
    if dry_run:
        model = DRY_MODEL
        run_kind = "dry-run"
        evidence = "not-fleet-evidence"
    else:
        from .case_live import LiveTriageModel, assert_no_key_leak, resolve_model_pin

        model = resolve_model_pin(cfg, model_pin)
        run_kind = "live"
        evidence = "fleet-evidence-candidate"
    wing = Wing(case_path, seed=seed)
    disc = resolve_disclosures(profile=wing.profile)
    patient_id = wing.record.get("id")
    if patient_id != IMM01_PATIENT_ID:
        raise CheckFail("WG-CASE-PATIENT-ID", f"expected {IMM01_PATIENT_ID}, got {patient_id}")
    trace: list[dict] = [meta_header(run_kind, evidence, model, cfg["name"], seed, disc, patient_id)]
    abstain_any = False

    imm = wing.record.scenario.get("immunology") or {}
    backend = LocalStubBackend()
    case_date = wing.now()

    if dry_run:
        llm = ScriptedModel(model, seed, script_from_cfg(cfg), trace)
    else:
        llm = LiveTriageModel(model, seed, trace, post=post)

    def triage(agent: str, question_id: str, context: dict) -> str:
        if dry_run:
            return llm.triage(agent, question_id, context)
        return llm.triage(agent, question_id, context, patient_id, case_date[:10])

    emit(trace, model, op="admit", patient=patient_id, at=case_date)

    state = triage("intake", "proceed_immunology_workup", {"ige_band": imm.get("ige_band")})
    if state == "abstain":
        abstain_any = True
        emit(trace, model, op="human_route", reason="intake_abstain", agent="intake")
        wing.trace("human_route", agent="intake")
    elif state == "no":
        raise CheckFail("WG-CASE-INTAKE-DECLINED", state)
    else:
        emit(trace, model, op="intake_ok", agent="intake")

    lab_order = deterministic_lab_order(imm)
    emit(trace, model, op="lab_order_selected", order_id=lab_order, by="deterministic")

    ack = triage("lab_gate", "ack_panel", {"order_id": lab_order})
    if ack == "abstain":
        abstain_any = True
        emit(trace, model, op="human_route", reason="lab_gate_abstain", agent="lab_gate")
        wing.trace("human_route", agent="lab_gate")
    elif ack != "yes":
        raise CheckFail("WG-CASE-LAB-DECLINED", ack)

    tool_jobs = [("orders_computer", {"order_id": lab_order, "patient": wing.record.get("id")}, seed + 1)]
    tool_results = await gather_tools(backend, tool_jobs)
    for tr in tool_results:
        emit(trace, model, op="tool_result", **tr)
        if tr.get("status") != "completed":
            raise CheckFail("WG-CASE-TOOL-FAIL", tr.get("tool", "?"))

    approved = imm.get("approved_pm_form")
    pm_ok = triage("pm_planner", "raise_pm_plan", {"approved_form": approved})
    if pm_ok == "abstain":
        abstain_any = True
        emit(trace, model, op="human_route", reason="pm_abstain", agent="pm_planner")
    elif pm_ok == "yes":
        form_id = approve_pm_form(approved, approved)
        pm_jobs = [("forms_computer", {"form_id": form_id, "patient": wing.record.get("id"),
                                        "planning_only": True, "note": "paperwork only; no sequences"}, seed + 2)]
        pm_results = await gather_tools(backend, pm_jobs)
        for tr in pm_results:
            emit(trace, model, op="tool_result", **tr)

    # Positive control: planted unapproved form must be caught, not propagated.
    planted = imm.get("planted_trap_form")
    plant_caught = False
    try:
        triage("pm_planner", "trap_unapproved", {"form_id": planted})
        approve_pm_form(planted, approved)
    except CheckFail as e:
        if e.id == "WG-CASE-UNAPPROVED-FORM":
            plant_caught = True
            emit(trace, model, op="plant_caught", check_id=e.id, form_id=planted)
        else:
            raise
    if not plant_caught:
        raise CheckFail("WG-CASE-PLANT-MISSED", "unapproved form was not caught")

    wing.record_exit("discharge")
    wing.close()
    emit(trace, model, op="exit", type="discharge")

    for line in trace:
        if line.get("kind") == "model_call":
            line.setdefault("model", model)
            for k in PARAM_KEYS:
                line.setdefault("params", {}).setdefault(k, None)

    apply_manifest_abstain(trace[0], disc, abstain_any)
    ok = plant_caught and all(r.get("status") == "completed" for r in tool_results)
    if not dry_run:
        import os
        from ward import live
        from .case_live import assert_no_key_leak

        key = os.environ.get(live.KEY_ENV, "")
        assert_no_key_leak(key, json.dumps(trace, sort_keys=True, default=str))
    return {"fleet": cfg["name"], "seed": seed, "run_kind": run_kind, "evidence": evidence, "model": model,
            "patient": wing.record.get("id"), "plant_caught": plant_caught, "tool_calls": len(backend.calls),
            "model_calls": sum(1 for x in trace if x.get("kind") == "model_call"), "pass": ok, "trace": trace,
            "testing_banner": disc["testing_banner"], "patient_fit_note": disc["patient_fit_note"],
            "disclosures_plain": disc["disclosures_plain"],
            "abstain_label": disc["abstain_label"] if abstain_any else None,
            "abstain_plain": disc["abstain_plain"] if abstain_any else None, "abstain_any": abstain_any}


def run(
    dry_run: bool = True,
    case_path: pathlib.Path = CASE,
    fleet_path: pathlib.Path = FLEET,
    model_pin: str | None = None,
    post=None,
) -> dict:
    cfg = load_fleet(fleet_path)
    return asyncio.run(_run_async(cfg, dry_run, case_path, model_pin=model_pin, post=post))


def write_trace(out: dict, path: pathlib.Path) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in out["trace"]))


def summary_line(out: dict) -> str:
    return (f"run_kind={out['run_kind']} evidence={out['evidence']} fleet={out['fleet']} seed={out['seed']} "
            f"model={out['model']} pass={out['pass']} plant_caught={out['plant_caught']} "
            f"tool_calls={out['tool_calls']} model_calls={out['model_calls']}")


def result_block_lines(out: dict) -> list[str]:
    lines = [out["testing_banner"], out["patient_fit_note"], *out["disclosures_plain"]]
    if out.get("abstain_any"):
        lines.extend([out["abstain_label"], out["abstain_plain"]])
    lines.append(summary_line(out))
    lines.append(f"trace={out.get('trace_path', '')}")
    return lines


def print_result_block(out: dict) -> None:
    for line in result_block_lines(out):
        if line.startswith("trace=") and not out.get("trace_path"):
            continue
        print(line)


def main(argv=None):
    import os
    os.environ.setdefault("WING_PROFILE", str(ROOT / "profiles" / "test.toml"))
    os.environ.setdefault("WING_WARD_DIR", str(ROOT / "ward"))
    p = argparse.ArgumentParser(description="Run one synthetic immunology fleet case (traced).")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Scripted model; trace is not fleet evidence (default).")
    p.add_argument("--live", action="store_true", help="OpenRouter live triage (requires ward model API key env).")
    p.add_argument(
        "--model",
        metavar="PIN",
        help="Dated model snapshot pin for --live (overrides fleet toml model when set).",
    )
    p.add_argument("-o", "--output", type=pathlib.Path, default=pathlib.Path("immunology_trace.jsonl"))
    p.add_argument("--case", type=pathlib.Path, default=CASE)
    p.add_argument("--fleet", type=pathlib.Path, default=FLEET, help="Fleet toml (e.g. fleets/ward/immunology_mvp.toml).")
    args = p.parse_args(argv)
    dry = not args.live
    out = run(dry_run=dry, case_path=args.case, fleet_path=args.fleet, model_pin=args.model)
    if not out["pass"]:
        raise CheckFail("WG-CASE-RUN-FAILED", summary_line(out))
    write_trace(out, args.output)
    out["trace_path"] = str(args.output.resolve())
    trace_text = args.output.read_text()
    if not dry:
        import os

        from ward import live

        from .case_live import assert_no_key_leak
        from .evidence import pack_and_verify_live_trace

        key = os.environ.get(live.KEY_ENV, "")
        assert_no_key_leak(key, trace_text, "\n".join(result_block_lines(out)))
        merkle = pack_and_verify_live_trace(args.output)
        if merkle:
            print(f"merkle_root={merkle}")
    print_result_block(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""LIVE fleet: each staff reply in wing.fleet goes through ward's guarded OpenRouter send (ward.live_client, pinned
dated model; any other model fails the run). A dry run (trace mode, same seed) counts the replies first; the run is
refused if the estimate would take total spend over the hard cap. Results are LIVE and provisional."""
import json, os, pathlib
from . import fleet
from ward import live, live_client

CAP_USD = 1.00
PRICE_IN, PRICE_OUT = 0.66e-6, 1.98e-6               # OpenRouter deepseek/deepseek-v4-pro-0813, $ per token
TOKENS_IN = 1000                                     # ceiling per reply (prompt is ~300); out is the client's max_tokens
PER_REPLY = TOKENS_IN * PRICE_IN + 120 * PRICE_OUT
LEDGER = pathlib.Path(os.environ.get("WING_LIVE_LEDGER", "/workspace/tmp/live_spend.json"))
SITUATION = {"help_heard": "the patient or family pressed for help; tell them they were heard",
             "help_on_way": "an escalation was sent; tell the patient help is on the way",
             "own_words_ask": "ask the patient if they want to add their own words for the team",
             "meds_unreviewed": "tell the patient their medicines are not yet checked"}


class OverCap(RuntimeError):
    pass


def spent():
    return json.loads(LEDGER.read_text())["usd"] if LEDGER.is_file() else 0.0


def estimate(c):
    return fleet.run(c)["replies"] * PER_REPLY        # trace dry run: same schedule, no network


def make_reply(seed, lines, post=None):
    send = live_client.make_send(seed, **({"post": post} if post else {}))
    choices = sorted(set(lines.values()))
    key_of = {v: k for k, v in lines.items()}

    def reply(rec_in):
        rec = {"patient": rec_in["patient"], "date": rec_in["date"], "choices": choices,
               "situation": SITUATION[key_of[rec_in["expected_line"]]],
               "instruction": "You are a ward staff agent in a synthetic test. Pick the one signed line id for the "
                              'situation. Reply with JSON {"line_id": "<id>"} only.'}
        got = live.send_guarded([rec], send)            # guard first; a non-pinned model raises ModelMismatch
        return {"model": send.models[-1], "expected_line": rec_in["expected_line"], "line_id": got.get("line_id"),
                "changes": sorted(set(got) - {"line_id"}), "text_ok": True, "events": {}}
    return reply


def run(c, post=None):
    est = estimate(c)
    if spent() + est > CAP_USD:
        raise OverCap(f"spent {spent():.4f} + estimate {est:.4f} > cap {CAP_USD}")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps({"usd": spent() + est}))      # charged at the ceiling before sending
    try:
        out = fleet.run(c, mode="live", reply=make_reply(c["seed"], fleet.load_profile().get("lines"), post))
        out["error"] = None
    except Exception as e:                                       # mismatch, bad reply, refusal: the run fails
        out = {"label": "LIVE provisional", "fleet": c["name"], "seed": c["seed"], "error": f"{type(e).__name__}: {e}"}
    out.update(estimate_usd=round(est, 4), model_pin=live_client.MODEL)
    out["clean"] = out["error"] is None and not out.get("fails") and not out.get("not_answered") \
        and all(r["model"] == live_client.MODEL for r in out.get("records", []))
    key = os.environ.get(live.KEY_ENV)
    if key and key in json.dumps(out, default=str):
        raise RuntimeError("key found in a live result; nothing written")
    return out


if __name__ == "__main__":       # python3 -m wing.fleet_live FLEET.toml OUT.json SEED [SEED ...]
    import copy, sys
    base, res = fleet.load(sys.argv[1]), []
    for s in sys.argv[3:]:
        c = copy.deepcopy(base); c["seed"] = int(s)
        res.append(run(c))
    pathlib.Path(sys.argv[2]).write_text(json.dumps(res, indent=1, default=str))
    for o in res:
        print(o["seed"], "CLEAN" if o["clean"] else "FAIL", o.get("replies"), o.get("fails"), o.get("slips"),
              o.get("false_alarms"), o.get("extra_night_wakeups"), o["error"], o["estimate_usd"])
    print("ledger_usd", round(spent(), 4))

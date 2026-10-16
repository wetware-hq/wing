"""LIVE fleet connector, offline: ward's client with a fake post. Pinned model, guards, cap and key hygiene."""
import copy, json, pathlib
import pytest
from wing import fleet, fleet_live
from ward import live, live_client

FULL = fleet.load(pathlib.Path(__file__).resolve().parent.parent / "fleets" / "wing_full.toml")
KEY = "sk-or-FAKE-KEY-0000"


def post_ok(model=live_client.MODEL, extra=None):
    def post(body, key):
        rec = json.loads(body["messages"][1]["content"])[0]
        lid = {v: k for k, v in fleet_live.SITUATION.items()}[rec["situation"]]
        out = {"line_id": fleet.load_profile().get("lines")[lid], **(extra or {})}
        return {"model": model, "choices": [{"message": {"content": json.dumps(out)}}]}
    return post


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv(live.CLOCK_ENV, "test")
    monkeypatch.setenv(live.KEY_ENV, KEY)
    monkeypatch.setattr(fleet_live, "LEDGER", tmp_path / "spend.json")


def test_clean_live_run_with_pinned_model():
    o = fleet_live.run(FULL, post_ok())
    assert o["clean"] and o["replies"] > 0 and KEY not in json.dumps(o, default=str)
    assert {r["model"] for r in o["records"]} == {live_client.MODEL}


def test_other_model_fails_run():
    o = fleet_live.run(FULL, post_ok(model="other/model-2025"))
    assert not o["clean"] and o["error"].startswith("ModelMismatch")


def test_extra_change_in_reply_fails():
    o = fleet_live.run(FULL, post_ok(extra={"zone": "lower"}))
    assert not o["clean"] and set(o["fails"]) == {"PM-EXTRA-CHANGE"}


def test_clock_guard_on(monkeypatch):
    monkeypatch.setenv(live.CLOCK_ENV, "real")
    o = fleet_live.run(FULL, post_ok())
    assert not o["clean"] and "RF-LIVE-CLOCK-NOT-TEST" in o["error"]


def test_cap_refuses_before_send():
    fleet_live.LEDGER.write_text(json.dumps({"usd": fleet_live.CAP_USD - 0.001}))
    with pytest.raises(fleet_live.OverCap):
        fleet_live.run(FULL, post_ok())


def test_estimate_is_small_and_charged():
    est = fleet_live.estimate(FULL)
    assert 0 < est < 0.1
    fleet_live.run(FULL, post_ok())
    assert abs(fleet_live.spent() - est) < 1e-9


def test_key_in_result_is_refused():
    with pytest.raises(RuntimeError, match="key found"):
        fleet_live.run(copy.deepcopy(FULL), post_ok(model=KEY))


def test_planted_undersize_still_fails():
    from wing import CheckFail
    with pytest.raises(CheckFail):
        fleet.load(pathlib.Path(__file__).resolve().parent.parent / "fleets" / "planted_undersize.toml")

"""wing shows only signed v2 lines, each pinned by its own sha256 from line_pins.toml. Unconfirmed pins or DRAFT /
RE-SIGN lines are PENDING (skipped, never passed) and keep wing not stable."""
import hashlib
import pytest
from conftest import caught
from wing import CheckFail, lines

if not lines.V2.is_file():
    pytest.skip(f"v2 wording not mounted at {lines.V2}", allow_module_level=True)


def _pins(tmp_path, text_by_id, status="confirmed"):
    p = tmp_path / "pins.toml"
    p.write_text(f'status = "{status}"\n[sha256]\n' + "".join(
        f'"{i}" = "{hashlib.sha256(t.encode()).hexdigest()}"\n' for i, t in text_by_id.items()))
    return p


def _v2(tmp_path, text):
    p = tmp_path / "v2.md"; p.write_text(text); return p


GOOD = "| LT-MEDS-UNCHANGED-PT | Your doctor checked this medicine and it stays the same. | v2 |\n" \
       "| LT-REACH-HEARD-PT | We heard you. [Role] is coming to see you within [time]. Press the call button. | v2 |\n"


def test_v2_file_full_digest_pinned():
    assert lines.file_pin() == "491c36f5a8a863dff0c9bf681f8d5a859cea40f9ba7403fe1e54f5da78100b48"
    assert {"LT-REACH-HEARD-PT", "LT-REACH-ONWAY-PT"} <= set(lines.pins()[1])


def test_tampered_one_character_file_edit(tmp_path):
    raw = lines.V2.read_bytes()
    i = raw.index(b"heard you") + 1
    p = tmp_path / "v2_lines_SIGNED.md"; p.write_bytes(raw[:i] + b"E" + raw[i + 1:])
    caught("WG-LINE-FILE-HASH", lines.line, "LT-MEDS-UNCHANGED-PT", p)


def test_help_line_selected_by_time_on_record():
    a = lines.help_heard({"role": "The nurse", "minutes": 30})
    b = lines.help_heard({"role": "The nurse"})
    assert "within 30 minutes" in a and b.startswith("We heard you. The nurse is on the way.")


@pytest.mark.parametrize("lid", lines.used().values())
def test_used_line_is_signed_and_pinned(lid):
    try:
        assert lines.line(lid)
    except CheckFail as e:
        if e.id in ("WG-LINE-PIN-PENDING", "WG-LINE-DRAFT"):
            pytest.skip(f"PENDING {e.id} {lid}")
        raise


def test_pinned_line_displays(tmp_path):
    v = _v2(tmp_path, GOOD); pins = _pins(tmp_path, {"LT-MEDS-UNCHANGED-PT": "Your doctor checked this medicine and it stays the same."})
    assert lines.line("LT-MEDS-UNCHANGED-PT", v, pins).startswith("Your doctor")


def test_tampered_one_word_changed(tmp_path):
    pins = _pins(tmp_path, {"LT-MEDS-UNCHANGED-PT": "Your doctor checked this medicine and it stays the same."})
    v = _v2(tmp_path, GOOD.replace("Your doctor checked", "Your doctor approved"))
    caught("WG-LINE-HASH", lines.line, "LT-MEDS-UNCHANGED-PT", v, pins)


def test_tampered_draft_line_refused(tmp_path):
    v = _v2(tmp_path, GOOD.replace("same. | v2 |", "same. | v2 DRAFT |"))
    caught("WG-LINE-DRAFT", lines.line, "LT-MEDS-UNCHANGED-PT", v, _pins(tmp_path, {}))


def test_tampered_unconfirmed_pin_file(tmp_path):
    t = "Your doctor checked this medicine and it stays the same."
    caught("WG-LINE-PIN-PENDING", lines.line, "LT-MEDS-UNCHANGED-PT", _v2(tmp_path, GOOD),
           _pins(tmp_path, {"LT-MEDS-UNCHANGED-PT": t}, status="awaiting final confirm"))


def test_tampered_unsigned_id():
    caught("WG-LINE-UNSIGNED", lines.line, "LT-NOT-A-LINE")


def test_help_heard_time_only_from_assignment(tmp_path):
    t = "We heard you. [Role] is coming to see you within [time]. Press the call button."
    v, p = _v2(tmp_path, GOOD), _pins(tmp_path, {"LT-REACH-HEARD-PT": t})
    assert "within 30 minutes" in lines.help_heard({"role": "The nurse", "minutes": 30}, path=v, pin_file=p)
    caught("WG-LINE-UNSIGNED", lines.help_heard, {"role": "The nurse"}, path=v, pin_file=p)   # on-way line absent here


def test_tampered_help_heard_without_assignment():
    caught("WG-HELP-NO-ASSIGNMENT", lines.help_heard, {})

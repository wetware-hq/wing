"""wing shows only signed v2 lines, each pinned by sha256. A used line marked DRAFT fails its test (red until signed)."""
import pytest
from conftest import caught
from wing import lines


@pytest.mark.parametrize("lid", lines.USED)
def test_used_line_is_signed_and_pinned(lid):
    assert lines.line(lid)                    # raises WG-LINE-DRAFT while the line is DRAFT


def test_tampered_one_word_changed(tmp_path):
    src = lines.V2.read_text(encoding="utf-8")
    p = tmp_path / "v2.md"
    p.write_text(src.replace("Your doctor checked this medicine", "Your doctor approved this medicine"))
    caught("WG-LINE-HASH", lines.line, "LT-MEDS-UNCHANGED-PT", p)


def test_tampered_draft_line_refused(tmp_path):
    p = tmp_path / "v2.md"
    p.write_text(lines.V2.read_text(encoding="utf-8").replace("| v2; when review record missing |",
                                                              "| v2 DRAFT; when review record missing |"))
    caught("WG-LINE-DRAFT", lines.line, "LT-MEDS-UNREVIEWED-PT", p)


def test_tampered_unsigned_id():
    caught("WG-LINE-UNSIGNED", lines.line, "LT-NOT-A-LINE")

"""Every liability rule FLEET.toml declares as hard_fail must actually run.

n_terminal_glutamine and poly_q were declared in FLEET.toml and implemented
nowhere, so a binder carrying either was emitted with liability_filters.pass
= true. That value is one of the three hard gates.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ONE = ROOT / "fleets/campaigns/NYESO1-A0201/run-one"
FLEET = ROOT / "fleets/campaigns/NYESO1-A0201-specificity/FLEET.toml"
if str(RUN_ONE) not in sys.path:
    sys.path.insert(0, str(RUN_ONE))

import specificity_scoring as ss  # noqa: E402

CLEAN = "ELELEKASRAHVEVSYKAASGRLKGYVTSVEGK"  # no motif, no C, no M/W, no Q


def test_the_clean_control_sequence_passes():
    # If this ever fails the other assertions below prove nothing.
    r = ss.liability_filters(CLEAN)
    assert r["pass"] is True


def test_n_terminal_glutamine_is_a_hard_fail():
    r = ss.liability_filters("Q" + CLEAN[1:])
    assert r["pass"] is False
    assert r["n_terminal_glutamine"]["hard_fail"] is True


def test_an_internal_glutamine_is_not_an_n_terminal_one():
    r = ss.liability_filters(CLEAN[:5] + "Q" + CLEAN[6:])
    assert r["n_terminal_glutamine"]["hard_fail"] is False
    assert r["pass"] is True


def test_a_poly_q_run_over_the_declared_max_is_a_hard_fail():
    r = ss.liability_filters(CLEAN[:5] + "QQQ" + CLEAN[8:])
    assert r["pass"] is False
    assert r["poly_q"]["hard_fail"] is True
    assert r["poly_q"]["longest_run"] == 3


def test_a_poly_q_run_at_the_declared_max_is_allowed():
    r = ss.liability_filters(CLEAN[:5] + "QQ" + CLEAN[7:])
    assert r["poly_q"]["hard_fail"] is False
    assert r["poly_q"]["longest_run"] == 2
    assert r["pass"] is True


# --------------------------------------------------------------------------
# The implementation's defaults are duplicated from FLEET.toml rather than read
# from it. Turn silent drift between the two into a failing test.
# --------------------------------------------------------------------------


def _declared() -> dict:
    return tomllib.loads(FLEET.read_text())["liability_filters"]


def test_the_motif_list_matches_the_one_fleet_toml_declares():
    assert ss.DEFAULT_MOTIFS == _declared()["motif_scan"]


def test_the_poly_q_max_run_matches_the_one_fleet_toml_declares():
    assert ss.DEFAULT_POLY_Q_MAX_RUN == _declared()["poly_q"]["max_run"]


def test_fleet_toml_still_declares_both_rules_as_hard_fail():
    d = _declared()
    assert d["n_terminal_glutamine"] == "hard_fail"
    assert d["poly_q"]["mode"] == "hard_fail"

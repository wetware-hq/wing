import os, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from wing import CheckFail

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("WING_PROFILE", str(ROOT / "profiles" / "test.toml"))
os.environ.setdefault("WING_WARD_DIR", str(ROOT / "ward"))
os.environ.setdefault("WARD_SIBLINGS_DIR", str(ROOT))
ANS = pathlib.Path(__file__).resolve().parent.parent / "scenarios" / "W01.toml"
WARD_FLEETS = ROOT / "fleets" / "ward"


def fleet_override(src, dest, lines):
    """Copy a ward fleet toml with whole lines replaced (key -> replacement line), everything else byte-identical.
    Fixtures that differ from a shipped fleet by a few keys are built this way instead of being near-copies on disk."""
    text = pathlib.Path(src).read_text()
    for key, line in lines.items():
        text, n = re.subn(rf"^{re.escape(key)}\s*=.*$", line.replace("\\", "\\\\"), text, count=1, flags=re.M)
        assert n == 1, f"{key} not found in {src}"
    dest = pathlib.Path(dest)
    dest.write_text(text)
    return dest


@pytest.fixture(scope="session")
def planted_undersize(tmp_path_factory):
    """Was fleets/planted_undersize.toml (78 loc, 76 identical to wing_full.toml): wing_full with two keys
    overridden. Built here so it cannot drift from the base ward config it is meant to be a planted copy of."""
    return fleet_override(
        WARD_FLEETS / "wing_full.toml",
        tmp_path_factory.mktemp("fleets") / "planted_undersize.toml",
        {"name": 'name = "planted_undersize"   # PLANTED: must fail WG-FLEET-UNDERSIZE-PATIENTS',
         "num_patients": "num_patients = 6             # beds"},
    )


@pytest.fixture(scope="session")
def abstain_fleet(tmp_path_factory):
    """Was fleets/immunology_abstain.toml (15 loc, 12 identical to immunology_mvp.toml): the mvp case fleet with
    one scripted answer flipped to abstain."""
    return fleet_override(
        WARD_FLEETS / "immunology_mvp.toml",
        tmp_path_factory.mktemp("fleets") / "immunology_abstain.toml",
        {"name": 'name = "immunology_abstain"',
         "seed": "seed = 19362",
         "lab_gate_ack_panel": 'lab_gate_ack_panel = "abstain"'},
    )


def caught(check_id, fn, *a, **k):
    """A tampered run is caught ONLY if it fails with its target check id; anything else is not caught."""
    try:
        fn(*a, **k)
    except CheckFail as e:
        assert e.id == check_id, f"failed with {e.id}, not target {check_id}"
        return True
    except Exception as e:                                 # crash / unrelated error: NOT caught
        pytest.fail(f"not caught: {type(e).__name__}: {e}")
    pytest.fail(f"not caught: {check_id} never raised")

import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from wing import CheckFail

ANS = pathlib.Path(__file__).resolve().parent.parent / "scenarios" / "W01.toml"


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

"""wing: orchestrates ward (and, behind the same plug, the other rooms). One clock, guards and trace: ward's."""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DEFAULT_WARD = os.path.join(_ROOT, "ward")
if not os.path.isdir(_DEFAULT_WARD):
    _DEFAULT_WARD = os.path.join(os.path.dirname(_ROOT), "ward")
WARD_DIR = os.environ.get("WING_WARD_DIR", _DEFAULT_WARD)
if WARD_DIR not in sys.path:
    sys.path.insert(0, WARD_DIR)


class CheckFail(Exception):
    """A check failed. .id is the stable check id; a tampered run is caught only by its target id."""
    def __init__(self, check_id, detail=""):
        self.id = check_id
        super().__init__(f"{check_id}: {detail}")

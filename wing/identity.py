"""Positive identification before every write (S16 wrong-patient). Compared ONLY with the separate patient record
of the intended patient, never with the target chart. Fallback when the patient cannot answer: the ID band only."""
from . import CheckFail


def confirm(record, evidence):
    """evidence: {"against": "record"|..., "method": "name_dob"|"id_band"|..., "can_answer": bool, ...values}.
    Returns a check entry to attach to the write; raises on any failure with its own id."""
    if evidence.get("against") != "record":
        raise CheckFail("WP-ID-CHECKED-AGAINST-CHART", str(evidence.get("against")))
    m = evidence.get("method")
    if m == "name_dob":
        if not evidence.get("can_answer", True):
            raise CheckFail("WP-ID-FALLBACK-NOT-BAND", "patient cannot answer: band only")
        ok = (evidence.get("name"), evidence.get("dob")) == (record.get("name"), record.get("dob"))
    elif m == "id_band":
        ok = evidence.get("band") == record.get("band")
    else:
        raise CheckFail("WP-ID-FALLBACK-NOT-BAND", str(m))
    if not ok:
        raise CheckFail("WP-ID-MISMATCH", record.get("id"))
    return {"patient": record.get("id"), "method": m}


def write(wing, entry, value, check=None):
    """A write to the intended patient's record carries the identity check made for it, or it is refused."""
    if not check or check.get("patient") != wing.record.get("id"):
        raise CheckFail("WP-ID-CHECK-SKIPPED", wing.record.get("id"))
    wing.trace("write", entry=entry, patient=check["patient"], id_method=check["method"])
    return True

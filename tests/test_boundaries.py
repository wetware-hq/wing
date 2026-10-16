"""Every zone edge tested at the value and one step either side, from the profile's own bands (generic TEST profiles)."""
import pathlib
import pytest
from wing import CheckFail, profile

P = pathlib.Path(__file__).resolve().parent.parent / "profiles"


def edges(pr):
    for vital, spec in pr.get("vital_zones").items():
        b, step = spec["bands"], spec["step"]
        for (lo1, hi1, z1), (lo2, hi2, z2) in zip(b, b[1:]):
            yield vital, step, hi1, z1, lo2, z2


def _profile(name):
    try:
        pr = profile.Profile(P / f"{name}.toml")
        pr.get("vital_zones")
        return pr
    except CheckFail as e:
        if e.id in ("WG-PROFILE-PENDING", "WG-PROFILE-UNSIGNED"):
            pytest.skip(f"PENDING: {name} {e.id}")
        raise


@pytest.mark.parametrize("name", ["test", "test-b"])
def test_every_edge_value_and_one_step_either_side(name):
    pr = _profile(name)
    n = 0
    for vital, step, hi1, z1, lo2, z2 in edges(pr):
        assert round(lo2 - hi1, 6) == step, f"{vital}: gap/overlap between {hi1} and {lo2}"
        assert profile.vital_zone(pr, vital, round(hi1 - step, 6)) == z1
        assert profile.vital_zone(pr, vital, hi1) == z1
        assert profile.vital_zone(pr, vital, lo2) == z2
        assert profile.vital_zone(pr, vital, round(lo2 + step, 6)) == z2
        n += 1
    assert n >= 1


def test_rr_example_24_25_26():
    pr = _profile("test")
    assert [profile.vital_zone(pr, "rr", v)[-1] for v in (24, 25, 26)] == ["0", "1", "1"]


def test_tampered_band_gap(tmp_path):
    from conftest import caught
    pr = _profile("test")
    pr._d["vital_zones"]["value"]["rr"]["bands"][2] = [11, 24, "x"]
    caught("WG-ZONE-GAP", profile.vital_zone, pr, "rr", 10)

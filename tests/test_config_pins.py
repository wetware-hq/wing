"""Guards for the unpinned-gate validator (Path B).

FLEET.toml declares gates whose inputs live in sibling YAML files. Several are
still TBD. Before this validator a run could report the calibration gate as held
when there was nothing to score, which is the most dangerous kind of green.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

CAMPAIGN = Path(__file__).resolve().parents[1] / "fleets/campaigns/NYESO1-A0201-specificity"
if str(CAMPAIGN) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN))

import config_pins  # noqa: E402

FLEET_PINNED = textwrap.dedent(
    """
    [calibration]
    scored_each_run = true
    anchors_file = "anchors.yaml"

    [species_cross_reactivity]
    panel = "orthologs.yaml"

    [manufacturability]
    status = "pinned"
    """
)

ANCHORS_PINNED = textwrap.dedent(
    """
    status: pinned
    anchors:
      - id: anchor_a
        sequence: EVQLVESGGG
    controls:
      - id: control_a
        sequence: EVQLVESGGG
    """
)

ORTHOLOGS_PINNED = textwrap.dedent(
    """
    orthologs:
      - species: mouse
        sequence: SLLMWITQC
      - species: cyno
        sequence: SLLMWITQC
    """
)


def _campaign(tmp_path: Path, *, fleet: str, anchors: str, orthologs: str) -> Path:
    (tmp_path / "FLEET.toml").write_text(fleet)
    (tmp_path / "anchors.yaml").write_text(anchors)
    (tmp_path / "orthologs.yaml").write_text(orthologs)
    return tmp_path / "FLEET.toml"


def test_fully_pinned_campaign_reports_all_pinned(tmp_path):
    toml = _campaign(
        tmp_path, fleet=FLEET_PINNED, anchors=ANCHORS_PINNED, orthologs=ORTHOLOGS_PINNED
    )
    report = config_pins.collect_unpinned(toml, tmp_path)
    assert report["all_pinned"] is True
    assert report["findings"] == []
    assert report["unpinned_gates"] == []


def test_a_tbd_ortholog_sequence_is_reported_not_silently_skipped(tmp_path):
    orthologs = ORTHOLOGS_PINNED.replace(
        "sequence: SLLMWITQC\n  - species: cyno", "sequence: TBD\n  - species: cyno"
    )
    toml = _campaign(
        tmp_path, fleet=FLEET_PINNED, anchors=ANCHORS_PINNED, orthologs=orthologs
    )
    report = config_pins.collect_unpinned(toml, tmp_path)
    assert report["all_pinned"] is False
    assert "species_cross_reactivity" in report["unpinned_gates"]
    assert any("mouse" in f["detail"] for f in report["findings"])


def test_a_deferred_anchors_file_fails_the_calibration_gate(tmp_path):
    anchors = ANCHORS_PINNED.replace("status: pinned", "status: deferred")
    toml = _campaign(
        tmp_path, fleet=FLEET_PINNED, anchors=anchors, orthologs=ORTHOLOGS_PINNED
    )
    report = config_pins.collect_unpinned(toml, tmp_path)
    assert "calibration" in report["unpinned_gates"]


def test_calibration_is_not_checked_when_the_gate_is_inactive(tmp_path):
    fleet = FLEET_PINNED.replace("scored_each_run = true", "scored_each_run = false")
    anchors = ANCHORS_PINNED.replace("status: pinned", "status: deferred")
    toml = _campaign(tmp_path, fleet=fleet, anchors=anchors, orthologs=ORTHOLOGS_PINNED)
    report = config_pins.collect_unpinned(toml, tmp_path)
    assert "calibration" not in report["unpinned_gates"]


def test_require_pinned_raises_and_names_every_unpinned_gate(tmp_path):
    fleet = FLEET_PINNED.replace('status = "pinned"', 'status = "TBD"')
    toml = _campaign(
        tmp_path, fleet=fleet, anchors=ANCHORS_PINNED, orthologs=ORTHOLOGS_PINNED
    )
    with pytest.raises(config_pins.UnpinnedGateError) as excinfo:
        config_pins.require_pinned(toml, tmp_path)
    assert "manufacturability" in str(excinfo.value)


def test_the_live_campaign_is_currently_unpinned(tmp_path):
    # Not aspirational: the anchors and ortholog sequences are deliberately TBD
    # rather than fabricated. This pins the validator to the real campaign so the
    # day someone pins them, this test is the reminder to retire the block.
    report = config_pins.collect_unpinned(CAMPAIGN / "FLEET.toml", CAMPAIGN)
    assert report["all_pinned"] is False

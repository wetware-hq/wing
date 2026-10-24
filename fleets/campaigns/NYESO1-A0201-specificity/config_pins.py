"""Refuse to let a declared gate pass vacuously because its inputs are unpinned.

FLEET.toml declares gates whose inputs live in sibling YAML files: the calibration
anchors, the ortholog panel, the manufacturability tool. Several of those are still
``TBD`` or ``deferred``. Nothing stopped a run from reporting that the calibration
gate held when there was nothing to score, which is the most dangerous kind of
green: a gate that is declared, never evaluated, and never seen to be missing.

``collect_unpinned`` reports what is unpinned. ``require_pinned`` raises. The
orchestrator records the report in the panel and refuses to hand off while a gate
it declares active is unpinned.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml

UNPINNED_SENTINELS = ("tbd", "deferred", "pending", "")


class UnpinnedGateError(RuntimeError):
    """A gate is declared active in FLEET.toml but its inputs are not pinned."""


def _is_unpinned(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in UNPINNED_SENTINELS
    return False


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _check_calibration(fleet: dict, campaign_dir: Path) -> list[dict]:
    cfg = fleet.get("calibration") or {}
    if not cfg:
        return []
    # scored_each_run declares the gate ACTIVE: it must have something to score.
    # Absent is NOT inactive. A typo or a deletion here used to disable the whole
    # calibration check silently, and the gate then vanished from unpinned_gates
    # instead of being reported as unevaluable.
    if "scored_each_run" not in cfg:
        return [
            {
                "gate": "calibration",
                "declared_active_by": "presence of [calibration] in FLEET.toml",
                "detail": (
                    "[calibration] declares no scored_each_run, so whether the gate "
                    "is active cannot be determined; it is treated as unpinned"
                ),
            }
        ]
    if not cfg.get("scored_each_run"):
        return []
    anchors_path = campaign_dir / str(cfg.get("anchors_file", "calibration_anchors.yaml"))
    doc = _load_yaml(anchors_path)
    findings: list[dict] = []
    if not doc:
        findings.append(
            {
                "gate": "calibration",
                "declared_active_by": "calibration.scored_each_run",
                "detail": f"anchors file not found or empty: {anchors_path.name}",
            }
        )
        return findings
    status = str(doc.get("status", "")).split("#")[0].strip().lower()
    if status != "pinned":
        findings.append(
            {
                "gate": "calibration",
                "declared_active_by": "calibration.scored_each_run",
                "detail": (
                    f"{anchors_path.name} status is {status!r}, not 'pinned'; "
                    "anchor sequences and per-axis thresholds are not fixed, so the "
                    "broken-rubric rule cannot be evaluated"
                ),
            }
        )
    for group in ("anchors", "controls"):
        for item in doc.get(group) or []:
            if _is_unpinned(item.get("sequence")):
                findings.append(
                    {
                        "gate": "calibration",
                        "declared_active_by": "calibration.scored_each_run",
                        "detail": f"{group} entry {item.get('id')!r} has no pinned sequence",
                    }
                )
    return findings


def _check_species_cross_reactivity(fleet: dict, campaign_dir: Path) -> list[dict]:
    cfg = fleet.get("species_cross_reactivity") or {}
    if not cfg:
        return []
    panel_path = campaign_dir / str(cfg.get("panel", "ortholog_panel.yaml"))
    doc = _load_yaml(panel_path)
    findings: list[dict] = []
    # A missing or empty panel file produced NO findings, so deleting or
    # renaming ortholog_panel.yaml made this gate report pinned. The calibration
    # check already flags its missing file; this one has to match.
    if not doc:
        return [
            {
                "gate": "species_cross_reactivity",
                "declared_active_by": "species_cross_reactivity.panel",
                "detail": f"ortholog panel file not found or empty: {panel_path.name}",
            }
        ]
    # The panel's own status is part of being pinned: pinning both sequences
    # while the document still says deferred is not a pinned gate.
    for label, value in (
        ("FLEET.toml species_cross_reactivity.status", cfg.get("status")),
        (f"{panel_path.name} status", doc.get("status")),
    ):
        if value is not None and _is_unpinned(value):
            findings.append(
                {
                    "gate": "species_cross_reactivity",
                    "declared_active_by": "species_cross_reactivity.panel",
                    "detail": f"{label} is {value!r}, which is not pinned",
                }
            )
    if not (doc.get("orthologs") or []):
        findings.append(
            {
                "gate": "species_cross_reactivity",
                "declared_active_by": "species_cross_reactivity.panel",
                "detail": f"{panel_path.name} declares no orthologs to score",
            }
        )
    for item in doc.get("orthologs") or []:
        if _is_unpinned(item.get("sequence")):
            findings.append(
                {
                    "gate": "species_cross_reactivity",
                    "declared_active_by": "species_cross_reactivity.panel",
                    "detail": f"{item.get('species')!r} ortholog sequence is not pinned",
                }
            )
    return findings


def _check_manufacturability(fleet: dict, _campaign_dir: Path) -> list[dict]:
    cfg = fleet.get("manufacturability") or {}
    if not cfg:
        return []
    status = str(cfg.get("status", "")).lower()
    if "tbd" in status or "pending" in status:
        return [
            {
                "gate": "manufacturability",
                "declared_active_by": "manufacturability.floor.mode = hard_floor",
                "detail": (
                    "the aggregation-propensity tool is not pinned, so the hard floor "
                    "cannot be enforced"
                ),
            }
        ]
    return []


_CHECKS = (_check_calibration, _check_species_cross_reactivity, _check_manufacturability)


def collect_unpinned(fleet_toml: Path, campaign_dir: Path | None = None) -> dict:
    """Report every declared gate whose inputs are unpinned."""
    campaign_dir = campaign_dir or fleet_toml.parent
    fleet = tomllib.loads(fleet_toml.read_text())
    findings: list[dict] = []
    for check in _CHECKS:
        findings.extend(check(fleet, campaign_dir))
    gates = sorted({f["gate"] for f in findings})
    return {
        "checked": [
            "calibration",
            "species_cross_reactivity",
            "manufacturability",
        ],
        "unpinned_gates": gates,
        "findings": findings,
        "all_pinned": not findings,
    }


def require_pinned(fleet_toml: Path, campaign_dir: Path | None = None) -> dict:
    """Raise UnpinnedGateError unless every declared gate has pinned inputs."""
    report = collect_unpinned(fleet_toml, campaign_dir)
    if not report["all_pinned"]:
        lines = [f"  - [{f['gate']}] {f['detail']}" for f in report["findings"]]
        raise UnpinnedGateError(
            "declared gates have unpinned inputs and cannot be evaluated:\n"
            + "\n".join(lines)
        )
    return report

"""Build the L1A (design) request body so declared targeting reaches the wire.

Run one submitted the whole peptide as epitope_residues ([0..8]) and sent no
non_binding_residues, while targeting_flags.json already declared hotspots on
peptide positions P4-P8 and FLEET.toml already staged three negative-design
panels. That drift is the failure mode this module exists to close: the request
body is built from the declared flags and the signed panel, not hand-edited.

Indexing (proved, not assumed):
  * Design API sequence path: 0-based per chain. FLEET.toml
    ``[target.chain_C] epitope_residues`` comment and PLATFORM.md both record
    "0-based, per-chain, verified live". Negative-design panels expand the same
    convention (``0-based index = mature author number - 1``).
  * targeting_flags.json hotspots / buried_anchors use 1-based mature / CIF
    author numbers (P4-P8 = [4,5,6,7,8]). Conversion: API index = author - 1.
  * Off-by-one here silently aims the designer at the wrong residues.

The prediction (L1B) API rejects epitope_residues / non_binding_residues; that
path stays in the child campaign's l1b_request_builder.py and is unchanged.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

PARENT = Path(__file__).resolve().parent
FLEET_PATH = PARENT / "FLEET.toml"
FLAGS_PATH = PARENT / "targeting_flags.json"
LEGACY_TEMPLATE = PARENT / "run-one" / "request-legacy-submitted.json"

# Declared hotspots in targeting_flags.json are 1-based author numbers P4-P8.
# Wire indices are 0-based on the design API sequence path.
EPITOPE_AUTHOR_1BASED = (4, 5, 6, 7, 8)
EPITOPE_API_0BASED = tuple(i - 1 for i in EPITOPE_AUTHOR_1BASED)  # (3, 4, 5, 6, 7)

# Anchors that must be in not-binding, not merely absent from binding.
# P2 and P9 are the buried MHC anchors (targeting_flags buried_anchors).
# P1 is named by the geometry brief as an anchor-class position; our engaging
# poses never contacted it. P3 is deliberately NOT listed: targeting_flags only
# call it "partly occluded", and the interface-geometry SASA measured binder
# burial against partners, not peptide-side solvent exposure, so inventing a
# buried status for P3 would be fabrication.
PEPTIDE_NON_BINDING_AUTHOR_1BASED = (1, 2, 9)
PEPTIDE_NON_BINDING_API_0BASED = tuple(i - 1 for i in PEPTIDE_NON_BINDING_AUTHOR_1BASED)

DEFAULT_PANEL = "targeted"  # OD-2, signed 2026-10-23

# Chain B is marked entirely in every panel (FLEET.toml negative_design_panels).
CHAIN_B_ALL = ["0-98"]


def _expand_ranges(ranges: list[str]) -> list[int]:
    out: list[int] = []
    for spec in ranges:
        if "-" in spec:
            a, b = spec.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(spec))
    return sorted(set(out))


def load_fleet(path: Path = FLEET_PATH) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def panels_from_fleet(fleet: dict | None = None) -> dict[str, dict[str, Any]]:
    """Return the three FLEET.toml panels keyed by name, with B marked entirely."""
    fleet = fleet if fleet is not None else load_fleet()
    out: dict[str, dict[str, Any]] = {}
    for pan in fleet["negative_design_panels"]:
        name = pan["name"]
        out[name] = {
            "name": name,
            "chain_A_marked": list(pan["chain_A_marked"]),
            "chain_B_marked": list(CHAIN_B_ALL),
            "recommended": bool(pan.get("recommended", False)),
            "rationale": pan.get("rationale", ""),
        }
    return out


def non_binding_residues_for_panel(
    panel: dict[str, Any],
    *,
    include_peptide_anchors: bool = True,
) -> dict[str, list[int]]:
    """Expand a panel into the legacy target-level non_binding_residues map.

    Indices are 0-based API indices. Peptide anchors are added on chain C when
    ``include_peptide_anchors`` is True, because the API distinguishes binding
    from not-binding and merely omitting anchors from epitope_residues leaves
    them free for the designer to use.
    """
    nb: dict[str, list[int]] = {}
    if "chain_A_marked" in panel:
        nb["A"] = _expand_ranges(panel["chain_A_marked"])
    if "chain_B_marked" in panel:
        nb["B"] = _expand_ranges(panel["chain_B_marked"])
    if include_peptide_anchors:
        nb["C"] = list(PEPTIDE_NON_BINDING_API_0BASED)
    return nb


def epitope_residues_api() -> list[int]:
    """Narrowed epitope as 0-based API indices for chain C."""
    return list(EPITOPE_API_0BASED)


def build_legacy_design_request(
    *,
    panel_name: str = DEFAULT_PANEL,
    num_proteins: int | None = None,
    fleet: dict | None = None,
) -> dict[str, Any]:
    """Build the LEGACY design body the hosted API actually accepts.

    Shape (PLATFORM.md / infra.json A4): ``{num_proteins, target{type:
    "no_template", entities, epitope_residues, non_binding_residues},
    binder_specification{...}}``. The migrated ``type:"binder"`` shape was
    rejected live on 2026-10-21 and is not produced here.
    """
    fleet = fleet if fleet is not None else load_fleet()
    panels = panels_from_fleet(fleet)
    if panel_name not in panels:
        raise ValueError(
            f"unknown panel {panel_name!r}; known: {sorted(panels)}"
        )
    panel = panels[panel_name]

    # Sequences come from the historical submitted body so we cannot silently
    # drift the target. Targeting fields are overwritten from declared intent.
    import json

    template = json.loads(LEGACY_TEMPLATE.read_text())
    body = {
        "num_proteins": (
            int(num_proteins)
            if num_proteins is not None
            else int(fleet.get("run_one", {}).get("num_proteins", template["num_proteins"]))
        ),
        "target": {
            "type": "no_template",
            "entities": template["target"]["entities"],
            "epitope_residues": {"C": epitope_residues_api()},
            "non_binding_residues": non_binding_residues_for_panel(panel),
        },
        "binder_specification": template["binder_specification"],
    }
    return body


def describe_panels(fleet: dict | None = None) -> dict[str, Any]:
    """What each panel would put on the wire (for the OD / report)."""
    fleet = fleet if fleet is not None else load_fleet()
    out: dict[str, Any] = {}
    for name, panel in panels_from_fleet(fleet).items():
        nb = non_binding_residues_for_panel(panel)
        out[name] = {
            "recommended": panel["recommended"],
            "active_default": name == DEFAULT_PANEL,
            "chain_A_n": len(nb.get("A", [])),
            "chain_B_n": len(nb.get("B", [])),
            "chain_C_non_binding": nb.get("C", []),
            "epitope_residues_C": epitope_residues_api(),
            "rationale": panel["rationale"],
        }
    return out

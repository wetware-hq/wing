"""Shared layer-2 scoring core for NYESO1-A0201 (local box + Modal).

Single implementation of ipSAE extraction, Tier 0 hooks, and bundle provenance so
``layer2_eval.py``, ``layer2_orchestrator.py``, and ``modal_layer2_app.py`` do not drift.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

RUN_ONE_JOB_ID = "prot_des_TY6KzyxULq8mACflXbhn"

LAYER2_PINS = {
    "base_image_digest": (
        "ghcr.io/wetware-hq/bindi-fleet-env"
        "@sha256:7e8762aebc3390611aafe0b67d925e567199d519e638113a80da33b86246a8e6"
    ),
    "worker_wheel": "bindi-0.2.0-py3-none-any.whl",
    "worker_wheel_sha256": (
        "6554960c1864ee3aabb64eccc7f639a78613daf2bb28b966abc27da1cb7d4e42"
    ),
    "worker_commit": "70b6c6c",
    "binder_chain": "D",
    "contact_cutoff_angstrom": 4.0,
}


def design_paths(design_dir: Path) -> dict[str, Path | None]:
    """Canonical artifact paths for one ``pres_*`` directory."""
    did = design_dir.name
    cif = design_dir / f"{did}_predicted.cif"
    pae = design_dir / "pae.npz"
    metrics = design_dir / "metrics.json"
    return {
        "cif": cif if cif.is_file() else None,
        "pae": pae if pae.is_file() else None,
        "metrics": metrics if metrics.is_file() else None,
    }


def provenance_block(design_id: str, design_dir: Path, artifacts_root: Path) -> dict[str, Any]:
    paths = design_paths(design_dir)
    rel = lambda p: str(p.relative_to(artifacts_root)) if p else None
    return {
        "design_id": design_id,
        "display_alias": f"NYESO1-{design_id}",
        "job_id": RUN_ONE_JOB_ID,
        "artifact_paths": {
            "predicted_cif": rel(paths["cif"]),
            "pae_npz": rel(paths["pae"]),
            "metrics_json": rel(paths["metrics"]),
        },
        "pins": dict(LAYER2_PINS),
    }


def score_ipsae_record(
    design_id: str,
    cif_path: Path,
    pae_path: Path,
    metrics_path: Path | None = None,
) -> dict[str, Any]:
    """ipSAE + pLDDT block matching legacy ``layer2_results.json`` when bindi is installed."""
    rec: dict[str, Any] = {
        "has_cif": cif_path.is_file(),
        "has_pae": pae_path.is_file(),
        "has_metrics": bool(metrics_path and metrics_path.is_file()),
    }
    if metrics_path and metrics_path.is_file():
        m = json.loads(metrics_path.read_text())
        rec["iptm"] = m.get("iptm")
        rec["complex_plddt_metrics_json"] = m.get("complex_plddt")
    else:
        rec["iptm"] = None
        rec["complex_plddt_metrics_json"] = None

    try:
        from bindi.ipsae import parse_predicted_cif, score_from_paths, TokenAlignmentError
    except ImportError:
        rec["score_error"] = "ImportError: bindi.ipsae unavailable in this environment"
        rec["parse_error"] = rec["score_error"]
        return rec

    try:
        parsed = parse_predicted_cif(str(cif_path))
        by: dict[str, list[float]] = {}
        for r in parsed.residues:
            by.setdefault(r.chain_id, []).append(r.plddt)
        allv = np.concatenate([np.asarray(v) for v in by.values()])
        rec["plddt_std_all"] = float(np.std(allv))
        rec["plddt_mean_all"] = float(np.mean(allv))
        rec["chain_mean_plddt"] = {k: float(np.mean(v)) for k, v in by.items()}
        rec["chain_len"] = {k: len(v) for k, v in by.items()}
        rec["parse_error"] = None
    except Exception as e:  # noqa: BLE001
        rec["parse_error"] = f"{type(e).__name__}: {e}"

    try:
        s = score_from_paths(str(pae_path), str(cif_path))
        rec["n_tokens"] = s["n_tokens"]
        rec["ipsae_ordered"] = s["ordered"]
        rec["pairs"] = s["pairs"]
        rec["min_ipsae_overall"] = min(v["min_ipsae"] for v in s["pairs"].values())
        dpairs = {k: v["min_ipsae"] for k, v in s["pairs"].items() if "D" in k.split("|")}
        rec["min_ipsae_D_pairs"] = dpairs
        rec["plddt_block"] = s["plddt"]
        rec["score_error"] = None
    except TokenAlignmentError as e:
        rec["score_error"] = f"TokenAlignmentError: {e}"
    except Exception as e:  # noqa: BLE001
        rec["score_error"] = f"{type(e).__name__}: {e}"
    return rec


def legacy_ipsae_map(design_records: dict[str, dict]) -> dict[str, dict]:
    """Strip orchestrator wrapper keys for ``layer2_results.json`` compatibility."""
    out: dict[str, dict] = {}
    for did, block in design_records.items():
        ipsae = block.get("ipsae") or {}
        out[did] = {k: v for k, v in ipsae.items() if k != "design_id"}
    return out

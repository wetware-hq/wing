"""Shared layer-2 scoring core for NYESO1-A0201 (local box + Modal).

ipSAE extraction, item-10 rigid-body docking, provenance, and legacy ipSAE export.
"""

from __future__ import annotations

import json
import math
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


def write_ipsae_only(artifacts_root: Path, out_path: Path) -> int:
    """Container/Modal path: ipSAE-only JSON (former ``layer2_eval.py``)."""
    out: dict[str, dict] = {}
    for d in sorted(p for p in artifacts_root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        paths = design_paths(d)
        if paths["cif"] and paths["pae"]:
            out[d.name] = score_ipsae_record(d.name, paths["cif"], paths["pae"], paths["metrics"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True))
    return 0 if out else 1


# --- UPGRADES.md item 10 (rigid-body re-derivation; not affinity evidence) ---

_ITEM10_CONTACT_CUTOFF = 4.0
_ITEM10_N_ROTATIONS = 72


def _item10_rotation_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / (np.linalg.norm(axis) + 1e-12)
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    return np.array(
        [
            [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
        ],
        dtype=float,
    )


def _item10_fibonacci_rotations(n: int) -> list[np.ndarray]:
    mats: list[np.ndarray] = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (2 * i + 1) / n
        r = math.sqrt(max(0.0, 1 - y * y))
        theta = golden * i
        axis = np.array([math.cos(theta) * r, y, math.sin(theta) * r], dtype=float)
        angle = math.pi * 0.35 * ((i % 7) + 1) / 7.0
        mats.append(_item10_rotation_matrix(axis, angle))
    return mats


def measure_item10_docking(cif_path: Path, peptide_sequence: str | None = None) -> dict[str, Any]:
    from contact_analysis import (
        B2M_CHAIN,
        BINDER_CHAIN,
        HEAVY_CHAIN,
        PEPTIDE_CHAIN,
        assert_layout,
        load_chains,
    )

    chains = load_chains(cif_path)
    assert_layout(chains, cif_path, peptide_sequence)

    target_all = np.concatenate(
        [chains[c].coords for c in (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN)], axis=0
    )
    binder_all = chains[BINDER_CHAIN].coords
    ch = chains[BINDER_CHAIN]
    ca_designed = np.asarray(
        [
            binder_all[ch.atom_seq_ids == resid].mean(axis=0)
            for resid in sorted(set(int(x) for x in ch.atom_seq_ids))
        ],
        dtype=float,
    )

    def contact_fraction(b_coords: np.ndarray) -> float:
        if len(b_coords) == 0:
            return 0.0
        d = np.linalg.norm(b_coords[:, None, :] - target_all[None, :, :], axis=-1)
        hit = (d <= _ITEM10_CONTACT_CUTOFF).any(axis=1)
        return float(hit.sum()) / float(len(b_coords))

    com = binder_all.mean(axis=0)
    best_score = -1.0
    best_coords = binder_all
    for rot in _item10_fibonacci_rotations(_ITEM10_N_ROTATIONS):
        trial = (binder_all - com) @ rot.T + com
        score = contact_fraction(trial)
        if score > best_score:
            best_score = score
            best_coords = trial

    ca_rederived = np.asarray(
        [
            best_coords[ch.atom_seq_ids == resid].mean(axis=0)
            for resid in sorted(set(int(x) for x in ch.atom_seq_ids))
        ],
        dtype=float,
    )

    def ca_rmsd(a: np.ndarray, b: np.ndarray) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return float("nan")
        a, b = a[:n], b[:n]
        mc, tc = a.mean(0), b.mean(0)
        h = (a - mc).T @ (b - tc)
        u, _, vt = np.linalg.svd(h)
        r = vt.T @ u.T
        if np.linalg.det(r) < 0:
            vt[-1, :] *= -1
            r = vt.T @ u.T
        aligned = (r @ a.T).T + tc
        return float(np.sqrt(np.mean(np.sum((aligned - b) ** 2, axis=1))))

    designed_cf = contact_fraction(binder_all)
    rederived_cf = contact_fraction(best_coords)
    return {
        "status": "RECORDED-NON-GATING",
        "method": (
            f"Fibonacci-sphere rigid-body search ({_ITEM10_N_ROTATIONS} rotations), "
            f"contact cutoff {_ITEM10_CONTACT_CUTOFF} Å; not affinity evidence"
        ),
        "pose_agreement_ca_rmsd_angstrom": round(ca_rmsd(ca_designed, ca_rederived), 4),
        "complementarity_contact_fraction_designed": round(designed_cf, 5),
        "complementarity_contact_fraction_rederived": round(rederived_cf, 5),
        "complementarity_contact_fraction_delta": round(rederived_cf - designed_cf, 5),
        "search_best_contact_fraction": round(best_score, 5),
    }


def evaluate_l2_policies(tier0: dict[str, Any], policies: tuple[str, ...] = ()) -> dict[str, str]:
    active = set(policies)
    out = {
        "item_3_buried_anchors_zero": "skipped",
        "item_5_pose_agreement": "skipped",
        "item_6_complementarity_delta": "skipped",
    }
    if "buried-anchors-zero" in active:
        n = tier0.get("item_3_buried_anchor_contact_count")
        if n is None:
            out["item_3_buried_anchors_zero"] = "skipped"
        elif n == 0:
            out["item_3_buried_anchors_zero"] = "pass"
        else:
            out["item_3_buried_anchors_zero"] = "fail"
    return out


def policy_violations(policy_results: dict[str, str]) -> list[str]:
    return [k for k, v in policy_results.items() if v == "fail"]

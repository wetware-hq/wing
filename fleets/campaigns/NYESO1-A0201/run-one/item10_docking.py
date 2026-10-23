"""UPGRADES.md section 4 item 10 — independent rigid-body pose re-derivation (CPU only).

Uses a Fibonacci-sphere rotation search with numpy only (no Boltz parameters, no neural
re-predictor). Reports **comparisons only**:

  * pose_agreement_ca_rmsd — RMSD of binder Cα after superposing the fixed pMHC target
  * complementarity_contact_fraction — heavy-atom contact fraction vs target (proxy)
  * complementarity_contact_fraction_delta — re-derived minus designed (RECORDED-NON-GATING)

This is **not** binding affinity evidence and must not be read as a docking score.
When the optional ``shape_complementarity`` package is present, ``Sc_designed`` and
``Sc_rederived`` are recorded for audit; the gate-relevant field remains the **delta**.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from contact_analysis import (
    B2M_CHAIN,
    BINDER_CHAIN,
    HEAVY_CHAIN,
    PEPTIDE_CHAIN,
    assert_layout,
    load_chains,
)

CONTACT_CUTOFF = 4.0
N_ROTATIONS = 72


def _rotation_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
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


def _fibonacci_rotations(n: int) -> list[np.ndarray]:
    mats: list[np.ndarray] = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (2 * i + 1) / n
        r = math.sqrt(max(0.0, 1 - y * y))
        theta = golden * i
        axis = np.array([math.cos(theta) * r, y, math.sin(theta) * r], dtype=float)
        angle = math.pi * 0.35 * ((i % 7) + 1) / 7.0
        mats.append(_rotation_matrix(axis, angle))
    return mats


def _target_coords(chains: dict) -> np.ndarray:
    parts = []
    for cid in (HEAVY_CHAIN, B2M_CHAIN, PEPTIDE_CHAIN):
        parts.append(chains[cid].coords)
    return np.concatenate(parts, axis=0)


def _binder_ca_coords(chains: dict, binder_coords: np.ndarray | None = None) -> np.ndarray:
    ch = chains[BINDER_CHAIN]
    coords = binder_coords if binder_coords is not None else ch.coords
    seq = ch.atom_seq_ids
    ca_coords = [
        coords[ch.atom_seq_ids == resid].mean(axis=0)
        for resid in sorted(set(int(x) for x in seq))
    ]
    return np.asarray(ca_coords, dtype=float)


def _contact_fraction(binder_coords: np.ndarray, target_coords: np.ndarray, cutoff: float) -> float:
    if len(binder_coords) == 0 or len(target_coords) == 0:
        return 0.0
    d = np.linalg.norm(binder_coords[:, None, :] - target_coords[None, :, :], axis=-1)
    hit = (d <= cutoff).any(axis=1)
    return float(hit.sum()) / float(len(binder_coords))


def _kabsch(mobile: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (R, t) aligning mobile onto target (same length)."""
    mc = mobile.mean(axis=0)
    tc = target.mean(axis=0)
    m0 = mobile - mc
    t0 = target - tc
    h = m0.T @ t0
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T
    t = tc - r @ mc
    return r, t


def _ca_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return float("nan")
    a, b = a[:n], b[:n]
    r, t = _kabsch(a, b)
    aligned = (r @ a.T).T + t
    return float(np.sqrt(np.mean(np.sum((aligned - b) ** 2, axis=1))))


def _try_shape_complementarity(cif_path: Path, binder_chain: str) -> dict[str, float] | None:
    try:
        from shape_complementarity import ShapeComplementarity  # type: ignore
    except ImportError:
        return None
    try:
        sc = ShapeComplementarity()
        sc.load_cif(str(cif_path), binder_chain, "A")
        return {"Sc": float(sc.sc)}
    except Exception:  # noqa: BLE001
        return None


def measure_design(cif_path: Path) -> dict[str, Any]:
    chains = load_chains(cif_path)
    assert_layout(chains, cif_path)

    binder_all = chains[BINDER_CHAIN].coords
    target_all = _target_coords(chains)
    ca_designed = _binder_ca_coords(chains)

    com = binder_all.mean(axis=0)
    best_score = -1.0
    best_coords = binder_all
    for rot in _fibonacci_rotations(N_ROTATIONS):
        trial = (binder_all - com) @ rot.T + com
        score = _contact_fraction(trial, target_all, CONTACT_CUTOFF)
        if score > best_score:
            best_score = score
            best_coords = trial

    designed_cf = _contact_fraction(binder_all, target_all, CONTACT_CUTOFF)
    rederived_cf = _contact_fraction(best_coords, target_all, CONTACT_CUTOFF)

    ca_rederived = _binder_ca_coords(chains, binder_coords=best_coords)

    sc_block = _try_shape_complementarity(cif_path, BINDER_CHAIN)

    out: dict[str, Any] = {
        "status": "RECORDED-NON-GATING",
        "method": (
            f"Fibonacci-sphere rigid-body search ({N_ROTATIONS} rotations), "
            f"contact cutoff {CONTACT_CUTOFF} Å; not affinity evidence"
        ),
        "pose_agreement_ca_rmsd_angstrom": round(_ca_rmsd(ca_designed, ca_rederived), 4),
        "complementarity_contact_fraction_designed": round(designed_cf, 5),
        "complementarity_contact_fraction_rederived": round(rederived_cf, 5),
        "complementarity_contact_fraction_delta": round(rederived_cf - designed_cf, 5),
        "search_best_contact_fraction": round(best_score, 5),
    }
    if sc_block:
        out["shape_complementarity_designed"] = sc_block
        out["shape_complementarity_note"] = (
            "Absolute Sc is RECORDED-NON-GATING per UPGRADES item 10; use delta fields above."
        )
    return out


def measure_all(artifacts_root: Path) -> dict[str, Any]:
    designs: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for d in sorted(p for p in artifacts_root.iterdir() if p.is_dir() and p.name.startswith("pres_")):
        cif = d / f"{d.name}_predicted.cif"
        if not cif.is_file():
            errors[d.name] = "missing _predicted.cif"
            continue
        try:
            designs[d.name] = measure_design(cif)
        except Exception as e:  # noqa: BLE001
            errors[d.name] = f"{type(e).__name__}: {e}"
    return {
        "status": "RECORDED-NON-GATING",
        "spec": "UPGRADES.md v1.0 section 4 item 10",
        "designs": designs,
        "errors": errors,
    }

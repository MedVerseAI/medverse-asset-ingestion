"""Normalization: bring assets whose frame/units are unknown ("raw") into RAS millimetres.

Ported from the legacy `infer_frame` (units from vertebral column length, axes from anatomical landmarks).
Categories (not groups) drive the inference, so it works for any source that provides the same semantics.
"""
from __future__ import annotations

import re

import numpy as np

BRAIN_CATS = {"cerebellum", "brainstem", "deep_gray_other", "basal_ganglia", "amygdala", "thalamus", "hippocampus",
              "ventricular_system", "white_matter"}
DEEP_CATS = {"deep_gray_other", "basal_ganglia", "amygdala", "thalamus", "hippocampus"}


def _unit(v):
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("degenerate direction")
    return v / n


def _angle(a, b):
    return float(np.degrees(np.arccos(np.clip(np.dot(_unit(a), _unit(b)), -1, 1))))


def infer_frame(units: list, gcfg: dict) -> dict:
    """units: dicts(points Nx3 raw, category, subcategory, side, names). -> frame info (raw -> RAS mm)."""
    info = {"applied": False, "confidence": "none", "messages": []}

    def pts(sel):
        arr = [u["points"] for u in units if sel(u)]
        return np.concatenate(arr) if arr else np.empty((0, 3))

    vert = pts(lambda u: u["category"] == "vertebra")
    factor = 1.0
    if len(vert) > 100:
        c = vert.mean(0)
        _, _, vt = np.linalg.svd(vert - c, full_matrices=False)
        proj = (vert - c) @ vt[0]
        length = float(proj.max() - proj.min())
        lo, hi = gcfg["vertebral_column_length_range_mm"]
        fits = [f for f in gcfg["unit_candidate_factors"] if lo <= length * f <= hi]
        info["vertebral_length_raw"] = length
        if len(fits) == 1:
            factor = fits[0]
        else:
            info["messages"].append(f"unit factor ambiguous/undetermined (length {length:.3f}, candidates {fits}); "
                                    "assuming 1.0 (millimetres)")
    else:
        info["messages"].append("no vertebrae available to infer units; assuming millimetres")
    info["unit_factor_to_mm"] = factor

    cortex = lambda u: u["category"] == "cerebral_cortex"                                   # noqa: E731
    brain_all = pts(lambda u: u["category"] in BRAIN_CATS or cortex(u))
    low_spine = pts(lambda u: u["category"] == "vertebra" and u["subcategory"] in ("lumbar", "sacral"))
    cord = pts(lambda u: u["category"] == "spinal_cord")
    left = pts(lambda u: u["side"] == "L" and (cortex(u) or u["category"] in DEEP_CATS))
    right = pts(lambda u: u["side"] == "R" and (cortex(u) or u["category"] in DEEP_CATS))
    frontal = pts(lambda u: cortex(u) and any(re.search(r"frontal", n) and not re.search(r"nerve", n) for n in u["names"]))
    occip = pts(lambda u: cortex(u) and any("occipital" in n for n in u["names"]))
    cereb = pts(lambda u: u["category"] == "cerebellum")
    bstem = pts(lambda u: u["category"] == "brainstem")
    try:
        if len(brain_all) == 0:
            raise ValueError("no brain geometry")
        lower = low_spine if len(low_spine) else cord
        if len(lower) == 0:
            raise ValueError("no spine / cord geometry for the superior-inferior axis")
        S = _unit(brain_all.mean(0) - lower.mean(0))
        if len(left) == 0 or len(right) == 0:
            raise ValueError("no left/right hemisphere landmarks")
        R = _unit(right.mean(0) - left.mean(0))
        cands = []
        if len(frontal) and len(occip):
            cands.append(_unit(frontal.mean(0) - occip.mean(0)))
        if len(cereb) and len(bstem):
            cands.append(_unit(bstem.mean(0) - cereb.mean(0)))
        if not cands:
            raise ValueError("no anterior-posterior landmarks")
        A = _unit(np.sum(cands, axis=0))
        angs = {"R-S": _angle(R, S), "A-S": _angle(A, S), "R-A": _angle(R, A)}
        info["raw_axis_angles_deg"] = angs
        worst = max(abs(90.0 - a) for a in angs.values())
        Rn = _unit(R - S * np.dot(R, S))
        An = _unit(A - S * np.dot(A, S) - Rn * np.dot(A, Rn))
        M = np.vstack([Rn, An, S])
        info.update(matrix_raw_to_ras=M.tolist(), determinant=float(np.linalg.det(M)), applied=True,
                    worst_orthogonality_error_deg=worst,
                    confidence="ok" if worst <= gcfg["axis_orthogonality_tolerance_deg"] else "low")
        if len(cands) == 2:
            info["ap_landmark_disagreement_deg"] = _angle(cands[0], cands[1])
        if info["determinant"] < 0:
            info["messages"].append("raw frame is mirrored with respect to the anatomical labels; faces will be flipped")
        if info["confidence"] == "low":
            info["messages"].append(f"axes are only {90 - worst:.0f}..90 deg orthogonal: LOW confidence")
    except ValueError as exc:
        info["messages"].append(f"axis inference failed: {exc}; raw orientation kept")
        info["matrix_raw_to_ras"] = np.eye(3).tolist()
        info["determinant"] = 1.0
    return info


def frame_matrices(info: dict):
    """-> (T_unit 4x4 raw->mm, T_axes 4x4 mm-raw-axes -> RAS) so the two steps can be logged separately."""
    f = info["unit_factor_to_mm"]
    Tu = np.diag([f, f, f, 1.0])
    Ta = np.eye(4)
    Ta[:3, :3] = np.asarray(info["matrix_raw_to_ras"])
    return Tu, Ta

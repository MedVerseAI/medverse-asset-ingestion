"""Registration + coordinate-system validation."""
from __future__ import annotations

import numpy as np

from medverse.validation import Checks


def validate_registration(reg: dict, cfg: dict, meshes: dict, decisions: dict, volume_checks: dict) -> dict:
    """reg: registration result (or None); meshes: final MeshAssets by id; decisions: {entity_id: Decision}."""
    c = Checks()
    rc = cfg["registration"]
    if reg is None:
        c.add("registration_ran", "warn", "single-source run or registration skipped")
    else:
        c.check("scale_policy", abs(reg["scale_used"] - 1.0) < 1e-6 or rc["allow_scale"],
                f"scale {reg['scale_used']:.4f} applied with allow_scale=false")
        if abs(reg["scale_used"] - 1.0) > 1e-6:
            c.check("scale_justified", bool(reg["scale_reason"]), "scale without reason")
        lm = reg["diagnostics"].get("landmark_rms_mm")
        c.check("landmark_residual", lm is None or lm <= rc["landmark_max_residual_mm"],
                f"landmark RMS {lm} mm > {rc['landmark_max_residual_mm']}", level="warn",
                detail_ok="n/a (no shared landmarks)" if lm is None else f"{lm:.2f} mm")
        c.check("registration_confidence", reg["confidence"] == "ok", f"confidence={reg['confidence']}", level="warn")
    # orientation: left-labelled structures must lie at lower x than right-labelled ones (RAS)
    L = [m.vertices[:, 0].mean() for a, m in meshes.items() if decisions[a].side == "L"
         and decisions[a].semantic_category in ("cerebral_cortex", "thalamus", "basal_ganglia", "amygdala", "hippocampus")]
    R = [m.vertices[:, 0].mean() for a, m in meshes.items() if decisions[a].side == "R"
         and decisions[a].semantic_category in ("cerebral_cortex", "thalamus", "basal_ganglia", "amygdala", "hippocampus")]
    if L and R:
        xl, xr = float(np.mean(L)), float(np.mean(R))
        c.check("orientation_left_right", xl < xr, f"left mean x {xl:+.1f} mm >= right mean x {xr:+.1f} mm")
    else:
        c.add("orientation_left_right", "warn", "no L/R labelled structures to verify")
    # units: whole model extent must look like a human CNS / spine in mm
    if meshes:
        allv = np.concatenate([m.vertices for m in meshes.values()])
        ext = allv.max(0) - allv.min(0)
        c.check("units_mm", 80.0 < ext.max() < 1500.0, f"model max extent {ext.max():.1f} mm is not plausible for mm")
    for name, ok in volume_checks.items():
        c.check(name, ok, "violated")
    r = c.result()
    return r

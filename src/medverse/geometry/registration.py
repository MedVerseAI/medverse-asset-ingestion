"""Registration without geometric guessing.

Order (fixed by the specification):
  1. spatial metadata   -- both sources are already in RAS mm (NIfTI affine / inferred frame): T0 = identity
  2. initial alignment  -- real location information: landmark correspondences (else cloud centroids)
  3. landmarks          -- known reference structures (rigid; similarity only if allow_scale)
  4. reference geometry -- cortical surface clouds measure the fit
  5. ICP refinement     -- rigid trimmed ICP, bounded, accepted only if it improves the fit
allow_scale = false by default; a scale is only possible with a written reason and is recorded in provenance.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from medverse.core.transforms import decompose, rigid, rot_angle_deg, rot_from_euler_deg


def umeyama(src, dst, fix_scale=None):
    """Least-squares similarity dst ~ s*R@src + t (R proper rotation)."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    if len(src) == 0 or len(src) != len(dst):
        raise ValueError("umeyama() requires non-empty equal-length point arrays")
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1.0
    R = U @ S @ Vt
    if fix_scale is None:
        var_s = float((xs ** 2).sum() / len(src))
        if var_s < 1e-12:
            raise ValueError("degenerate point set with zero variance in umeyama()")
        s = float((D * np.diag(S)).sum() / var_s)
    else:
        s = float(fix_scale)
    return s, R, mu_d - s * (R @ mu_s)


def nearest(query, ref):
    """Exact nearest-neighbor lookup using scipy.spatial.cKDTree (O(N log M))."""
    query = np.asarray(query, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    if len(query) == 0 or len(ref) == 0:
        raise ValueError("nearest() requires non-empty query and ref arrays")
    tree = cKDTree(ref)
    dist, idx = tree.query(query)
    return np.asarray(idx, dtype=np.int64), np.asarray(dist, dtype=np.float64)


def stride_sample(points, n):
    if len(points) <= n:
        return points
    return points[np.linspace(0, len(points) - 1, n).astype(np.int64)]


def apply_T(points, T):
    return points @ T[:3, :3].T + T[:3, 3]


def trimmed_rms(moving_transformed, fixed, trim):
    """(trimmed RMS, median) of nearest distances moving -> fixed (aligned with ICP objective)."""
    _, d = nearest(moving_transformed, fixed)
    keep = d <= np.quantile(d, trim)
    return float(np.sqrt((d[keep] ** 2).mean())), float(np.median(d))


def _sim(s, R, t):
    T = np.eye(4)
    T[:3, :3] = s * R
    T[:3, 3] = t
    return T


def landmark_residuals(moving_lm, fixed_lm, T):
    out = {}
    for k in sorted(set(moving_lm) & set(fixed_lm)):
        p = apply_T(np.asarray(moving_lm[k])[None, :], T)[0]
        out[k] = float(np.linalg.norm(p - np.asarray(fixed_lm[k])))
    return out


def register(moving_cloud, fixed_cloud, moving_lm: dict, fixed_lm: dict, cfg: dict) -> dict:
    """cfg = config['registration'].  Returns {T (moving->fixed), stages[], diagnostics, confidence, scale_used}."""
    rc = cfg
    allow_scale = bool(rc["allow_scale"])
    stages, diag = [], {}
    T = np.eye(4)
    stages.append({"stage": "spatial_metadata", "applied": True, "note": "both sources are in RAS mm; T0 = identity"})
    have_clouds = moving_cloud is not None and fixed_cloud is not None and len(moving_cloud) and len(fixed_cloud)
    keys = sorted(set(moving_lm) & set(fixed_lm))
    rms_ref = None

    # ---- optional, explicit initial scale (legacy parity only) ------------------------------------------------
    s0 = 1.0
    if allow_scale and rc["scale_init"] != "none" and have_clouds:
        me = moving_cloud.max(0) - moving_cloud.min(0)
        fe = fixed_cloud.max(0) - fixed_cloud.min(0)
        ratios = fe / me
        s0 = float(ratios.min()) if rc["scale_init"] == "fit_inside" else float(np.exp(np.log(ratios).mean()))
        s0 = float(np.clip(s0, *rc["hard_scale_limits"]))
        c_m = (moving_cloud.min(0) + moving_cloud.max(0)) / 2
        c_f = (fixed_cloud.min(0) + fixed_cloud.max(0)) / 2
        T = _sim(s0, np.eye(3), c_f - s0 * c_m)
        stages.append({"stage": "initial_alignment", "method": f"bbox {rc['scale_init']} (legacy)", "scale": s0,
                       "reason": rc["scale_reason"]})
    # ---- 2/3. initial alignment from landmarks -------------------------------------------------------------------
    lm_used = False
    if len(keys) >= rc["landmark_min_count"]:
        src = np.array([moving_lm[k] for k in keys])
        dst = np.array([fixed_lm[k] for k in keys])
        s, R, t = umeyama(src, dst, fix_scale=None if allow_scale else 1.0)
        if allow_scale:
            s = float(np.clip(s, *rc["hard_scale_limits"]))
            s, R, t = umeyama(src, dst, fix_scale=s)
        cand = _sim(s, R, t)
        res = landmark_residuals(moving_lm, fixed_lm, cand)
        rms = float(np.sqrt(np.mean(np.square(list(res.values())))))
        ok = rms <= rc["landmark_max_residual_mm"]
        stages.append({"stage": "landmarks", "keys": keys, "residual_rms_mm": rms, "residuals": res,
                       "accepted": ok, "scale": s})
        if ok:
            T, lm_used = cand, True
    else:
        stages.append({"stage": "landmarks", "keys": keys, "accepted": False,
                       "note": f"need >= {rc['landmark_min_count']} matching landmarks, have {len(keys)}"})
    if not lm_used and not (allow_scale and rc["scale_init"] != "none") and have_clouds:
        T = rigid(t=fixed_cloud.mean(0) - moving_cloud.mean(0))      # centroid translation, rotation = identity
        stages.append({"stage": "initial_alignment", "method": "cloud centroids (no usable landmarks)"})
    # ---- 4. reference geometry measures the fit -----------------------------------------------------------------
    if have_clouds:
        m_s = stride_sample(moving_cloud, rc["sample_points"])
        f_s = stride_sample(fixed_cloud, rc["sample_points"])
        f_tree = cKDTree(f_s)
        rms_ref, med = trimmed_rms(apply_T(m_s, T), f_s, rc["icp_trim_fraction"])
        stages.append({"stage": "reference_geometry", "trimmed_rms_mm": rms_ref, "median_mm": med,
                       "moving_points": int(len(moving_cloud)), "fixed_points": int(len(fixed_cloud))})
        # ---- 5. ICP refinement ---------------------------------------------------------------------------------
        if rc["use_icp"]:
            T0 = T.copy()
            s_c, R_c, t_c = decompose(T)
            lo = max(s_c * rc["icp_scale_bounds"][0], rc["hard_scale_limits"][0])
            hi = min(s_c * rc["icp_scale_bounds"][1], rc["hard_scale_limits"][1])
            prev = rms_ref
            it = 0
            for it in range(rc["icp_iterations"]):
                moved = apply_T(m_s, _sim(s_c, R_c, t_c))
                d, j = f_tree.query(moved)
                keep = d <= np.quantile(d, rc["icp_trim_fraction"])
                src, dst = m_s[keep], f_s[j[keep]]
                if allow_scale:
                    ns, nR, nt = umeyama(src, dst)
                    if ns < lo or ns > hi:
                        ns, nR, nt = umeyama(src, dst, fix_scale=float(np.clip(ns, lo, hi)))
                else:
                    ns, nR, nt = umeyama(src, dst, fix_scale=1.0)
                s_c, R_c, t_c = ns, nR, nt
                rms = float(np.sqrt((d[keep] ** 2).mean()))
                if abs(prev - rms) < 1e-4:
                    break
                prev = rms
            Ticp = _sim(s_c, R_c, t_c)
            rms1, med1 = trimmed_rms(apply_T(m_s, Ticp), f_s, rc["icp_trim_fraction"])
            Rrel = Ticp[:3, :3] / s_c @ (T0[:3, :3] / decompose(T0)[0]).T
            ang = rot_angle_deg(Rrel)
            # Measure true anatomical centroid displacement (invariant to world-origin offset)
            c_m = m_s.mean(0, keepdims=True)
            shift = float(np.linalg.norm(apply_T(c_m, Ticp)[0] - apply_T(c_m, T0)[0]))
            st = {"stage": "icp", "iterations": it + 1, "trimmed_rms_mm": rms1, "median_mm": med1,
                  "rotation_deg": ang, "translation_mm": shift, "scale": s_c}
            if ang > rc["max_rotation_deg"]:
                st.update(accepted=False, rejected=f"rotation {ang:.1f} deg exceeds max_rotation_deg")
            elif shift > rc["max_translation_mm"]:
                st.update(accepted=False, rejected=f"translation {shift:.1f} mm exceeds max_translation_mm")
            elif rms1 >= rms_ref:
                st.update(accepted=False, rejected="did not improve the fit")
            else:
                st["accepted"] = True
                T = Ticp
            stages.append(st)
    else:
        stages.append({"stage": "reference_geometry", "applied": False, "note": "no reference cloud on both sides"})
    # ---- manual overrides (explicit, logged) --------------------------------------------------------------------
    if any(rc["manual_rotation_deg"]) or any(rc["manual_translation_mm"]):
        M = rigid(rot_from_euler_deg(*rc["manual_rotation_deg"]), rc["manual_translation_mm"])
        T = M @ T
        stages.append({"stage": "manual_override", "rotation_deg": rc["manual_rotation_deg"],
                       "translation_mm": rc["manual_translation_mm"]})
    s_final = decompose(T)[0]
    if abs(s_final - 1.0) > 1e-6 and not allow_scale:                       # defensive: must never happen
        raise RuntimeError("scale applied although registration.allow_scale = false")
    residuals = landmark_residuals(moving_lm, fixed_lm, T)
    lm_rms = float(np.sqrt(np.mean(np.square(list(residuals.values()))))) if residuals else None
    rms_final = trimmed_rms(apply_T(stride_sample(moving_cloud, rc["sample_points"]), T),
                            stride_sample(fixed_cloud, rc["sample_points"]),
                            rc["icp_trim_fraction"])[0] if have_clouds else None
    if lm_rms is not None and lm_rms <= rc["landmark_max_residual_mm"] and (lm_used or rms_final is not None):
        conf = "ok"
    elif rms_final is not None and not residuals:
        conf = "low"
    else:
        conf = "low" if lm_rms is None or lm_rms > rc["landmark_max_residual_mm"] else "ok"
    diag.update(landmark_rms_mm=lm_rms, landmark_residuals=residuals, reference_rms_mm=rms_final)
    return {"T": T, "stages": stages, "diagnostics": diag, "confidence": conf, "scale_used": s_final,
            "scale_reason": rc["scale_reason"] if abs(s_final - 1.0) > 1e-9 else ""}

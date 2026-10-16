"""Numerical helpers and registration routines for anatomical integration.

Function implementations are preserved from the original single-file script.
"""
import os
import re
import json
import math
import collections
import numpy as np
from integration_config import *

_PLY_TYPES = {"char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1", "short": "<i2", "ushort": "<u2",
              "int16": "<i2", "uint16": "<u2", "int": "<i4", "uint": "<u4", "int32": "<i4", "uint32": "<u4",
              "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8"}


# -----------------------------------------------------------------------------
# Read a binary PLY anatomical mesh produced by the exporter.
# Parameters / return behavior: see the unchanged function signature and body.
# Parses the PLY header and binary payload and returns numeric vertices and faces.
# -----------------------------------------------------------------------------
def read_ply_binary(path):
    """Read a binary_little_endian triangle PLY (as written by both export scripts).
    Returns verts (N,3) float64, faces (M,3) int64, rgb (N,3) uint8 or None."""
    with open(path, "rb") as fh:
        data = fh.read()
    end = data.find(b"end_header")
    if end < 0:
        raise ValueError("no PLY header")
    nl = data.find(b"\n", end)
    header = data[:nl].decode("ascii", errors="replace").splitlines()
    body = nl + 1
    if not any(l.strip() == "format binary_little_endian 1.0" for l in header):
        raise ValueError("only binary_little_endian PLY is supported")
    elements, cur = [], None
    for l in header:
        p = l.split()
        if not p:
            continue
        if p[0] == "element":
            cur = {"name": p[1], "count": int(p[2]), "props": []}
            elements.append(cur)
        elif p[0] == "property" and cur is not None:
            if p[1] == "list":
                cur["props"].append(("list", p[4], p[2], p[3]))
            else:
                cur["props"].append(("scalar", p[2], p[1]))
    verts = faces = rgb = None
    off = body
    for el in elements:
        if el["name"] == "vertex":
            dt = np.dtype([(pr[1], _PLY_TYPES[pr[2]]) for pr in el["props"] if pr[0] == "scalar"])
            arr = np.frombuffer(data, dtype=dt, count=el["count"], offset=off)
            off += dt.itemsize * el["count"]
            verts = np.stack([arr["x"], arr["y"], arr["z"]], 1).astype(np.float64)
            if all(k in arr.dtype.names for k in ("red", "green", "blue")):
                rgb = np.stack([arr["red"], arr["green"], arr["blue"]], 1).astype(np.uint8)
        elif el["name"] == "face":
            lp = el["props"][0]
            if lp[0] != "list":
                raise ValueError("unexpected face property")
            dt = np.dtype([("n", _PLY_TYPES[lp[2]]), ("idx", _PLY_TYPES[lp[3]], (3,))])
            arr = np.frombuffer(data, dtype=dt, count=el["count"], offset=off)
            off += dt.itemsize * el["count"]
            if len(arr) and not (arr["n"] == 3).all():
                raise ValueError("non-triangular faces are not supported")
            faces = arr["idx"].astype(np.int64)
        else:                                                       # skip unknown element (fixed size only)
            raise ValueError(f"unsupported PLY element '{el['name']}'")
    if verts is None or faces is None:
        raise ValueError("PLY has no vertex/face element")
    return verts, faces, rgb


# -----------------------------------------------------------------------------
# Read a Brainnetome label lookup table.
# Parameters / return behavior: see the unchanged function signature and body.
# Parses region identifiers and names used to map Brainnetome geometry to semantic metadata.
# -----------------------------------------------------------------------------
def read_lut(path):
    """FreeSurfer style LUT: index name R G B A  ->  {id: (name, (r,g,b))}  (same parsing as export_bna_voxels)."""
    lut = {}
    if not os.path.exists(path):
        return lut
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5 or line.lstrip().startswith("#"):
                continue
            try:
                idx = int(parts[0])
                r, g, b = (int(x) for x in parts[-4:-1])
            except ValueError:
                continue
            lut[idx] = (parts[1], (r, g, b))
    return lut


# -----------------------------------------------------------------------------
# Create a filesystem- and Blender-safe anatomical name.
# Parameters / return behavior: see the unchanged function signature and body.
# Normalizes a source label so it can be used consistently as an object or material name.
# -----------------------------------------------------------------------------
def safe_name(name):
    """Create a filesystem- and Blender-safe anatomical name.

Normalizes a source label so it can be used consistently as an object or material name."""
    return "".join(c for c in name if c.isalnum() or c in "_-")


# -----------------------------------------------------------------------------
# Compute the axis-aligned bounding box of a point set.
# Parameters / return behavior: see the unchanged function signature and body.
# Returns the minimum and maximum coordinates along each axis.
# -----------------------------------------------------------------------------
def bbox(points):
    """Compute the axis-aligned bounding box of a point set.

Returns the minimum and maximum coordinates along each axis."""
    return points.min(0), points.max(0)


# -----------------------------------------------------------------------------
# Compute the rotation angle represented by a rotation matrix.
# Parameters / return behavior: see the unchanged function signature and body.
# Extracts the principal rotation magnitude in degrees.
# -----------------------------------------------------------------------------
def rot_angle_deg(R):
    """Compute the rotation angle represented by a rotation matrix.

Extracts the principal rotation magnitude in degrees."""
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0))))


# -----------------------------------------------------------------------------
# Build a rotation matrix from Euler angles expressed in degrees.
# Parameters / return behavior: see the unchanged function signature and body.
# Converts the supplied Euler rotation to the matrix convention used by the registration code.
# -----------------------------------------------------------------------------
def rot_from_euler_deg(rx, ry, rz):
    """Build a rotation matrix from Euler angles expressed in degrees.

Converts the supplied Euler rotation to the matrix convention used by the registration code."""
    a, b, c = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


# -----------------------------------------------------------------------------
# Convert a rotation matrix into Euler angles in degrees.
# Parameters / return behavior: see the unchanged function signature and body.
# Decomposes the matrix using the convention expected by the placement stage.
# -----------------------------------------------------------------------------
def euler_from_rot_deg(R):
    """Convert a rotation matrix into Euler angles in degrees.

Decomposes the matrix using the convention expected by the placement stage."""
    sy = math.hypot(R[0, 0], R[1, 0])
    if sy > 1e-9:
        x, y, z = math.atan2(R[2, 1], R[2, 2]), math.atan2(-R[2, 0], sy), math.atan2(R[1, 0], R[0, 0])
    else:
        x, y, z = math.atan2(-R[1, 2], R[1, 1]), math.atan2(-R[2, 0], sy), 0.0
    return tuple(float(np.degrees(v)) for v in (x, y, z))


# -----------------------------------------------------------------------------
# Convert a rotation matrix into axis-angle form.
# Parameters / return behavior: see the unchanged function signature and body.
# Returns the unit rotation axis and corresponding angle.
# -----------------------------------------------------------------------------
def axis_angle(R):
    """Convert a rotation matrix into axis-angle form.

Returns the unit rotation axis and corresponding angle."""
    ang = rot_angle_deg(R)
    if ang < 1e-6:
        return (0.0, 0.0, 1.0), 0.0
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(ax)
    return (tuple((ax / n).tolist()) if n > 1e-12 else (0.0, 0.0, 1.0)), ang


# -----------------------------------------------------------------------------
# Estimate a similarity transform between corresponding point sets.
# Parameters / return behavior: see the unchanged function signature and body.
# Computes rotation, translation, and scale using the Umeyama least-squares method.
# -----------------------------------------------------------------------------
def umeyama(src, dst, fix_scale=None):
    """Least-squares similarity dst ~ s * R @ src + t (R proper rotation)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1.0
    R = U @ S @ Vt
    var_s = float((xs ** 2).sum() / len(src))
    s = float((D * np.diag(S)).sum() / var_s) if fix_scale is None else float(fix_scale)
    t = mu_d - s * (R @ mu_s)
    return s, R, t


# -----------------------------------------------------------------------------
# Find nearest neighbors between two point sets.
# Parameters / return behavior: see the unchanged function signature and body.
# Computes nearest-point correspondences used by registration and residual analysis.
# -----------------------------------------------------------------------------
def nearest(query, ref, chunk=1024):
    """Brute-force nearest neighbour (numpy only; Blender does not ship scipy)."""
    idx = np.empty(len(query), dtype=np.int64)
    dist = np.empty(len(query), dtype=np.float64)
    r2 = (ref ** 2).sum(1)
    for i in range(0, len(query), chunk):
        q = query[i:i + chunk]
        d2 = (q ** 2).sum(1)[:, None] + r2[None, :] - 2.0 * (q @ ref.T)
        j = d2.argmin(1)
        idx[i:i + chunk] = j
        dist[i:i + chunk] = np.sqrt(np.maximum(d2[np.arange(len(q)), j], 0.0))
    return idx, dist


# -----------------------------------------------------------------------------
# Down-sample a point set using deterministic striding.
# Parameters / return behavior: see the unchanged function signature and body.
# Returns a reproducible subset without introducing random sampling.
# -----------------------------------------------------------------------------
def stride_sample(points, n):
    """Down-sample a point set using deterministic striding.

Returns a reproducible subset without introducing random sampling."""
    if len(points) <= n:
        return points
    return points[np.linspace(0, len(points) - 1, n).astype(np.int64)]


# -----------------------------------------------------------------------------
# Apply a similarity transform to a point set.
# Parameters / return behavior: see the unchanged function signature and body.
# Transforms points using scale, rotation, and translation parameters.
# -----------------------------------------------------------------------------
def apply_sim(points, s, R, t):
    """Apply a similarity transform to a point set.

Transforms points using scale, rotation, and translation parameters."""
    return s * (points @ R.T) + t


# -----------------------------------------------------------------------------
# Compute a robust RMS registration error after trimming outliers.
# Parameters / return behavior: see the unchanged function signature and body.
# Ranks residuals, discards the configured extreme values, and computes RMS on the retained correspondences.
# -----------------------------------------------------------------------------
def trimmed_rms(ref, moving, trim):
    """Compute a robust RMS registration error after trimming outliers.

Ranks residuals, discards the configured extreme values, and computes RMS on the retained correspondences."""
    _, d = nearest(ref, moving)
    keep = d <= np.quantile(d, trim)
    return float(np.sqrt((d[keep] ** 2).mean())), float(np.median(d))


# -----------------------------------------------------------------------------
# Register the BodyParts3D cortex reference cloud to Brainnetome cortex geometry.
# Parameters / return behavior: see the unchanged function signature and body.
# Builds a correspondence set and estimates the similarity transform aligning the two coordinate systems.
# -----------------------------------------------------------------------------
def register_cortex(bn_pts, ref_pts):
    """Returns dict(s, R, t, method, diagnostics). Maps BN (MNI mm) -> BP3D space (mm)."""
    diag = {}
    bn_lo, bn_hi = bbox(bn_pts)
    rf_lo, rf_hi = bbox(ref_pts)
    bn_ext, rf_ext = bn_hi - bn_lo, rf_hi - rf_lo
    ratios = rf_ext / bn_ext
    diag["bn_extent_mm"] = bn_ext.tolist()
    diag["ref_extent_mm"] = rf_ext.tolist()
    diag["axis_ratios"] = ratios.tolist()
    s0 = float(ratios.min()) if REG_SCALE_MODE == "fit_inside" else float(np.exp(np.log(ratios).mean()))
    s0 = float(np.clip(s0, *REG_HARD_SCALE_LIMITS))
    R = np.eye(3)
    t = (rf_lo + rf_hi) / 2.0 - s0 * ((bn_lo + bn_hi) / 2.0)
    s = s0
    diag["initial"] = {"scale": s0, "translation": t.tolist()}
    bn_s, rf_s = stride_sample(bn_pts, REG_SAMPLE_POINTS), stride_sample(ref_pts, REG_SAMPLE_POINTS)
    rms0, med0 = trimmed_rms(rf_s, apply_sim(bn_s, s, R, t), REG_ICP_TRIM_FRACTION)
    diag["rms_initial_mm"], diag["median_initial_mm"] = rms0, med0
    method = "bbox"
    if REG_USE_ICP:
        lo, hi = s0 * REG_ICP_SCALE_BOUNDS[0], s0 * REG_ICP_SCALE_BOUNDS[1]
        lo, hi = max(lo, REG_HARD_SCALE_LIMITS[0]), min(hi, REG_HARD_SCALE_LIMITS[1])
        cs, cR, ct = s, R.copy(), t.copy()
        prev = rms0
        accepted = False
        for it in range(REG_ICP_ITERATIONS):
            moved = apply_sim(bn_s, cs, cR, ct)
            j, d = nearest(rf_s, moved)
            keep = d <= np.quantile(d, REG_ICP_TRIM_FRACTION)
            src, dst = bn_s[j[keep]], rf_s[keep]
            ns, nR, nt = umeyama(src, dst)
            if ns < lo or ns > hi:
                ns = float(np.clip(ns, lo, hi))
                ns, nR, nt = umeyama(src, dst, fix_scale=ns)
            cs, cR, ct = ns, nR, nt
            rms = float(np.sqrt((d[keep] ** 2).mean()))
            if abs(prev - rms) < 1e-4:
                break
            prev = rms
        ang = rot_angle_deg(cR)
        rms1, med1 = trimmed_rms(rf_s, apply_sim(bn_s, cs, cR, ct), REG_ICP_TRIM_FRACTION)
        diag["icp"] = {"iterations": it + 1, "scale": cs, "rotation_deg": ang, "rms_mm": rms1, "median_mm": med1}
        if ang > REG_MAX_ROTATION_DEG:
            diag["icp"]["rejected"] = f"rotation {ang:.1f} deg exceeds REG_MAX_ROTATION_DEG"
        elif rms1 >= rms0:
            diag["icp"]["rejected"] = "did not improve the fit"
        else:
            s, R, t, method, accepted = cs, cR, ct, "bbox+ICP", True
        diag["icp"]["accepted"] = accepted
    diag["rms_final_mm"], diag["median_final_mm"] = trimmed_rms(rf_s, apply_sim(bn_s, s, R, t), REG_ICP_TRIM_FRACTION)
    return {"s": s, "R": R, "t": t, "method": method, "diag": diag}


# -----------------------------------------------------------------------------
# Register anatomical landmarks between BodyParts3D and Brainnetome/reference space.
# Parameters / return behavior: see the unchanged function signature and body.
# Matches available landmarks and estimates the transformation that minimizes landmark residuals.
# -----------------------------------------------------------------------------
def register_landmarks(bn_lm, bp_lm, fixed_scale=None):
    """Register anatomical landmarks between BodyParts3D and Brainnetome/reference space.

Matches available landmarks and estimates the transformation that minimizes landmark residuals."""
    keys = sorted(set(bn_lm) & set(bp_lm))
    if len(keys) < 4:
        return None
    src = np.array([bn_lm[k] for k in keys])
    dst = np.array([bp_lm[k] for k in keys])
    s, R, t = umeyama(src, dst, fix_scale=fixed_scale)
    return {"s": s, "R": R, "t": t, "method": "landmarks", "keys": keys, "diag": {}}


# -----------------------------------------------------------------------------
# Measure residual errors after landmark registration.
# Parameters / return behavior: see the unchanged function signature and body.
# Applies the candidate transform and reports per-landmark and aggregate geometric errors.
# -----------------------------------------------------------------------------
def landmark_residuals(bn_lm, bp_lm, s, R, t):
    """Measure residual errors after landmark registration.

Applies the candidate transform and reports per-landmark and aggregate geometric errors."""
    out = {}
    for k in sorted(set(bn_lm) & set(bp_lm)):
        p = apply_sim(np.asarray(bn_lm[k])[None, :], s, R, t)[0]
        out[k] = float(np.linalg.norm(p - np.asarray(bp_lm[k])))
    return out


# -----------------------------------------------------------------------------
# Estimate an affine transformation between corresponding point sets.
# Parameters / return behavior: see the unchanged function signature and body.
# Solves for the linear affine mapping used when a similarity transform is insufficient.
# -----------------------------------------------------------------------------
def affine(s, R, t):
    """Estimate an affine transformation between corresponding point sets.

Solves for the linear affine mapping used when a similarity transform is insufficient."""
    A = np.eye(4)
    A[:3, :3] = s * R
    A[:3, 3] = t
    return A


# -----------------------------------------------------------------------------
# Apply an affine transformation to points.
# Parameters / return behavior: see the unchanged function signature and body.
# Multiplies the point coordinates by the affine matrix and applies its translation component.
# -----------------------------------------------------------------------------
def apply_affine(A, pts):
    """Apply an affine transformation to points.

Multiplies the point coordinates by the affine matrix and applies its translation component."""
    return pts @ A[:3, :3].T + A[:3, 3]

"""
integrate_brainnetome_bodyparts3d.py            (run inside Blender 4.0+)
----------------------------------------------------------------------------
Combines
    * the Human Brainnetome cerebral cortex   (PLY pieces written by export_bna_voxels.py, MNI mm)
    * the processed BodyParts3D anatomy       (output of export_bodyparts3d.py, RAS mm)
into ONE registered, centered, unit-scaled anatomical model.

How the two datasets are registered (no hand-placed translations):
  1. BodyParts3D is already in RAS millimetres (export_bodyparts3d.py inferred units + axes from the data).
     The Brainnetome pieces are in MNI RAS mm; the script verifies hemisphere sign and extents.
  2. Initial similarity: bounding box of the BN cortex (regions 1..BN_CORTICAL_MAX_ID) vs the bounding box of
     the BodyParts3D cerebral-cortex reference cloud  -> scale ("largest scale at which the BN cortex fits")
     and translation.
  3. Trimmed similarity ICP between the two cortical surfaces refines scale / rotation / translation
     (bounded, so a bad fit can never run away).
  4. Independent validation: Brainnetome subcortical parcels (thalamus, caudate, putamen, pallidum, amygdala,
     hippocampus - read only for this purpose, never imported) are compared with the BodyParts3D structures.
  5. The whole model is optionally rotated back into the atlas (MNI) orientation, centered on the world origin
     and converted to Blender units.  All transforms are baked into the meshes (clean object transforms).

The BodyParts3D cortex is never imported.  Muscles are never imported (manifest flag + name guard + final audit).
"""
import os
import re
import json
import math
import collections
import numpy as np
import bpy

# ============================================================================
# CONFIGURATION  -- the two base paths
# ============================================================================
BRAINNETOME_BASE_PATH = r"C:\University\Graduation Project\HumanBrainnetome"
BODYPARTS3D_BASE_PATH = r"C:\University\Graduation Project\BodyParts3D_data"

# Derived locations (defaults match the two export scripts; change only if you moved things)
BN_PIECES_DIR = os.path.join(BRAINNETOME_BASE_PATH, "voxel_export_pieces")
BN_LUT_PATH = os.path.join(BRAINNETOME_BASE_PATH, "BN_Atlas_freesurfer", "BN_Atlas_246_LUT.txt")
BP3D_EXPORT_DIR = os.path.join(BODYPARTS3D_BASE_PATH, "bp3d_export_pieces")

# --- Brainnetome ------------------------------------------------------------
BN_CORTICAL_MAX_ID = 210          # ids 1..210 cortical; 211+ subcortical (same split as the original importer)
BN_REGION_GAP_SCALE = 1.0         # original importer used 0.96 (visible gaps). 1.0 = watertight neighbours
BN_LANDMARK_NAME_RX = collections.OrderedDict([   # LUT-name patterns of the BN subcortical parcels (validation only)
    ("thalamus", r"tha_"),
    ("caudate", r"^(vca|dca)_"),
    ("putamen", r"^(vmpu|dlpu)_"),
    ("globus_pallidus", r"^gp_"),
    ("amygdala", r"amyg"),
    ("hippocampus", r"hipp"),
])
BP3D_LANDMARK_LABEL_RX = collections.OrderedDict([
    ("thalamus", r"^(left |right )?thalamus$"),
    ("caudate", r"^(left |right )?caudate nucleus$"),
    ("putamen", r"^(left |right )?putamen$"),
    ("globus_pallidus", r"^(left |right )?globus pallidus$"),
    ("amygdala", r"^(left |right )?amygdala$"),
    ("hippocampus", r"^(left |right )?hippocampus$"),
])

# --- registration -------------------------------------------------------------
REG_SCALE_MODE = "fit_inside"     # "fit_inside": largest scale at which BN bbox fits the BP3D cortex bbox
                                  # "match_mean" : geometric mean of the three axis ratios
REG_USE_ICP = True
REG_SAMPLE_POINTS = 6000          # points per cloud used by ICP
REG_ICP_ITERATIONS = 40
REG_ICP_TRIM_FRACTION = 0.75      # use the closest 75 % of correspondences
REG_ICP_SCALE_BOUNDS = (0.85, 1.15)   # ICP scale relative to the initial bbox scale
REG_MAX_ROTATION_DEG = 20.0       # ICP rotation beyond this is rejected (falls back to the initial fit)
REG_HARD_SCALE_LIMITS = (0.7, 1.5)
REG_MANUAL_SCALE = None           # e.g. 1.03 to override the automatic scale
REG_MANUAL_TRANSLATION_MM = (0.0, 0.0, 0.0)   # extra translation of the BN cortex after registration (mm)
REG_MANUAL_ROTATION_DEG = (0.0, 0.0, 0.0)     # extra XYZ Euler rotation of the BN cortex (deg)

# --- final placement ------------------------------------------------------------
ORIENT_MODEL_TO_ATLAS = True      # rotate the whole model so the Brainnetome cortex keeps its MNI axes
CENTER_ON = "model_bbox"          # "model_bbox" | "cortex_bbox"
BLENDER_UNITS_PER_MM = 0.001      # 1 Blender unit = 1 m  -> the spine+head model is ~0.75 units tall
CLEAR_PREVIOUS_MODEL = True       # remove an earlier ANATOMICAL_MODEL before building (re-runnable)
SET_SOLID_MATERIAL_VIEWPORT = True

# --- guards -----------------------------------------------------------------------
MUSCLE_GUARD_RX = re.compile(r"\bmuscle|muscul(?!oskeletal)|myocardi|sphincter|diaphragm")
CORTEX_GUARD_RX = re.compile(r"\bgyrus\b|\bgyri\b|\blobule\b|(frontal|parietal|temporal|occipital|limbic) lobe|"
                             r"\binsula\b|^cortex of|cerebral cortex|prefrontal cortex")
CORTEX_GUARD_EXCEPT_RX = re.compile(r"hippocamp|archicortex")

# --- scene structure -----------------------------------------------------------------
ROOT_NAME = "ANATOMICAL_MODEL"
GROUP_TO_COLLECTIONS = {              # manifest group -> (system, collection)
    "CEREBELLUM": ("BRAIN", "CEREBELLUM"),
    "BRAINSTEM": ("BRAIN", "BRAINSTEM"),
    "SUBCORTICAL_STRUCTURES": ("BRAIN", "SUBCORTICAL_STRUCTURES"),
    "OTHER_BRAIN_STRUCTURES": ("BRAIN", "OTHER_BRAIN_STRUCTURES"),
    "CRANIAL_NERVES": ("BRAIN", "CRANIAL_NERVES"),
    "VERTEBRAE": ("SPINAL_SYSTEM", "VERTEBRAE"),
    "INTERVERTEBRAL_DISCS": ("SPINAL_SYSTEM", "INTERVERTEBRAL_DISCS"),
    "SPINAL_CORD": ("SPINAL_SYSTEM", "SPINAL_CORD"),
    "SPINAL_NERVES": ("SPINAL_SYSTEM", "SPINAL_NERVES"),
}
# (group, subgroup or None) -> RGBA ; consistent, low-saturation anatomical palette
BP3D_COLORS = {
    ("VERTEBRAE", None): (0.86, 0.82, 0.70, 1.0),
    ("INTERVERTEBRAL_DISCS", None): (0.30, 0.52, 0.72, 1.0),
    ("SPINAL_CORD", None): (0.95, 0.88, 0.50, 1.0),
    ("CEREBELLUM", None): (0.72, 0.55, 0.48, 1.0),
    ("BRAINSTEM", None): (0.78, 0.66, 0.58, 1.0),
    ("SUBCORTICAL_STRUCTURES", None): (0.66, 0.48, 0.55, 1.0),
    ("OTHER_BRAIN_STRUCTURES", None): (0.85, 0.85, 0.80, 1.0),
    ("OTHER_BRAIN_STRUCTURES", "white_matter"): (0.92, 0.91, 0.86, 1.0),
    ("OTHER_BRAIN_STRUCTURES", "ventricular_system"): (0.35, 0.60, 0.90, 1.0),
    ("CRANIAL_NERVES", None): (0.95, 0.80, 0.30, 1.0),
}
MATERIAL_PREFIX = "ANAT_"


# ============================================================================
# LOGGING
# ============================================================================
class Log:
    # -----------------------------------------------------------------------------
    # Initialize the logging helper used by the integration pipeline.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Stores the output path and prepares the in-memory log buffer.
    # -----------------------------------------------------------------------------
    def __init__(self):
        """Initialize the logging helper used by the integration pipeline.

Stores the output path and prepares the in-memory log buffer."""
        self.lines = []

    # -----------------------------------------------------------------------------
    # Record and print one integration-stage log message.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Accepts a message and severity, formats it consistently, stores it, and emits it to the console.
    # -----------------------------------------------------------------------------
    def __call__(self, msg=""):
        """Record and print one integration-stage log message.

Accepts a message and severity, formats it consistently, stores it, and emits it to the console."""
        print(msg)
        self.lines.append(str(msg))

    # -----------------------------------------------------------------------------
    # Write a separated integration-stage log section.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Creates a consistent heading for a major pipeline stage.
    # -----------------------------------------------------------------------------
    def section(self, title):
        """Write a separated integration-stage log section.

Creates a consistent heading for a major pipeline stage."""
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)


log = Log()
WARNINGS = []


# -----------------------------------------------------------------------------
# Emit a warning without stopping the integration pipeline.
# Parameters / return behavior: see the unchanged function signature and body.
# Prints a clearly marked warning message for recoverable or noteworthy conditions.
# -----------------------------------------------------------------------------
def warn(msg):
    """Emit a warning without stopping the integration pipeline.

Prints a clearly marked warning message for recoverable or noteworthy conditions."""
    WARNINGS.append(msg)
    log(f"[WARN] {msg}")


# ============================================================================
# PURE NUMPY HELPERS (no bpy)
# ============================================================================
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


# ============================================================================
# DATASET LOADING / VALIDATION
# ============================================================================
# -----------------------------------------------------------------------------
# Load Brainnetome anatomical regions into an intermediate scene representation.
# Parameters / return behavior: see the unchanged function signature and body.
# Reads the Brainnetome source geometry and metadata and prepares the cortex structures for integration.
# -----------------------------------------------------------------------------
def load_brainnetome():
    """Load Brainnetome anatomical regions into an intermediate scene representation.

Reads the Brainnetome source geometry and metadata and prepares the cortex structures for integration."""
    log.section("Brainnetome: loading + validation")
    log(f"BRAINNETOME_BASE_PATH : {BRAINNETOME_BASE_PATH}")
    log(f"pieces directory      : {BN_PIECES_DIR}")
    if not os.path.isdir(BN_PIECES_DIR):
        raise FileNotFoundError(f"Brainnetome pieces folder not found: {BN_PIECES_DIR} "
                                "(run export_bna_voxels.py first)")
    lut = read_lut(BN_LUT_PATH)
    if lut:
        log(f"LUT                   : {BN_LUT_PATH}  ({len(lut)} entries)")
    else:
        warn(f"LUT not found/readable: {BN_LUT_PATH}; names/colors come from the PLY files only")
    files = sorted(f for f in os.listdir(BN_PIECES_DIR) if f.lower().endswith(".ply"))
    pieces, sub = {}, {}
    rx = re.compile(r"^(\d+)_(.*)\.ply$", re.I)
    for f in files:
        m = rx.match(f)
        if not m:
            warn(f"ignoring PLY with unexpected name: {f}")
            continue
        rid, fname = int(m.group(1)), m.group(2)
        entry = {"id": rid, "file": os.path.join(BN_PIECES_DIR, f), "name": fname}
        if rid in lut and safe_name(lut[rid][0]) != fname:
            warn(f"region {rid}: file name '{fname}' differs from LUT name '{lut[rid][0]}'")
        (pieces if rid <= BN_CORTICAL_MAX_ID else sub)[rid] = entry
    if BN_CORTICAL_MAX_ID > 210:
        warn("BN_CORTICAL_MAX_ID > 210: Brainnetome subcortical parcels will duplicate BodyParts3D deep structures")
    log(f"PLY files: {len(files)} | cortical (<= {BN_CORTICAL_MAX_ID}): {len(pieces)} | subcortical: {len(sub)}")
    if lut:
        expected = {i for i in lut if 1 <= i <= BN_CORTICAL_MAX_ID}
        missing = sorted(expected - set(pieces))
        if missing:
            warn(f"{len(missing)} cortical LUT regions have no PLY: {missing[:20]}{' ...' if len(missing) > 20 else ''}")
        extra = sorted(set(pieces) - set(lut))
        if extra:
            warn(f"PLY regions not in LUT: {extra}")
    if not pieces:
        raise RuntimeError("no Brainnetome cortical pieces found")
    for rid in sorted(pieces):
        p = pieces[rid]
        v, f, rgb = read_ply_binary(p["file"])
        p["verts"], p["faces"] = v, f
        if rid in lut:
            p["label"], p["color"] = lut[rid][0], tuple(c / 255.0 for c in lut[rid][1])
        else:
            p["label"] = p["name"]
            p["color"] = tuple((rgb[0] / 255.0).tolist()) if rgb is not None and len(rgb) else (0.7, 0.7, 0.7)
        m = re.search(r"_([LR])$", p["label"])
        p["hemi"] = m.group(1) if m else ""
    # ---- frame verification (data-driven) ----
    L = [p["verts"] for p in pieces.values() if p["hemi"] == "L"]
    R_ = [p["verts"] for p in pieces.values() if p["hemi"] == "R"]
    frame = {"flip_x": False}
    if L and R_:
        xl, xr = np.concatenate(L)[:, 0].mean(), np.concatenate(R_)[:, 0].mean()
        log(f"mean x of *_L regions = {xl:+.1f} mm, of *_R regions = {xr:+.1f} mm")
        if xl > xr:
            frame["flip_x"] = True
            warn("Brainnetome left hemisphere lies at +x: axes look like LAS -> mirroring x to RAS")
    else:
        warn("cannot verify Brainnetome left/right orientation (no _L/_R region names)")
    allv = np.concatenate([p["verts"] for p in pieces.values()])
    lo, hi = bbox(allv)
    ext = hi - lo
    log(f"cortex bbox min {np.round(lo, 1).tolist()} max {np.round(hi, 1).tolist()} extent {np.round(ext, 1).tolist()} mm")
    if not (100 < ext[0] < 200 and 120 < ext[1] < 230 and 80 < ext[2] < 170):
        warn("Brainnetome extents are not in the typical MNI-mm range; units/space may differ from MNI mm")
    if abs((lo[0] + hi[0]) / 2) > 10:
        warn("Brainnetome cortex is not centred near x = 0: check that the pieces are in MNI space")
    if not (ext[1] >= ext[0] and ext[1] >= ext[2]):
        warn("longest Brainnetome axis is not y (anterior-posterior); axis order may differ from RAS")
    # ---- subcortical landmarks (read only, never imported) ----
    lm = {}
    for key, rxs in BN_LANDMARK_NAME_RX.items():
        for hemi in ("L", "R"):
            vs = []
            for rid, p in sub.items():
                nm = lut.get(rid, (p["name"], None))[0].lower()
                if re.search(rxs, nm) and nm.endswith("_" + hemi.lower()):
                    v, _, _ = read_ply_binary(p["file"])
                    vs.append(v)
            if vs:
                a = np.concatenate(vs)
                lm[f"{key}_{hemi}"] = ((a.min(0) + a.max(0)) / 2.0)
    log(f"Brainnetome subcortical landmarks (validation only): {sorted(lm)}")
    return {"pieces": pieces, "frame": frame, "landmarks": lm, "lut": lut}


# -----------------------------------------------------------------------------
# Load exported BodyParts3D PLY structures and their manifest metadata.
# Parameters / return behavior: see the unchanged function signature and body.
# Reads the exporter outputs, reconstructs structure records, and prepares them for Blender object creation.
# -----------------------------------------------------------------------------
def load_bodyparts3d():
    """Load exported BodyParts3D PLY structures and their manifest metadata.

Reads the exporter outputs, reconstructs structure records, and prepares them for Blender object creation."""
    log.section("BodyParts3D: loading + validation")
    log(f"BODYPARTS3D_BASE_PATH : {BODYPARTS3D_BASE_PATH}")
    mpath = os.path.join(BP3D_EXPORT_DIR, "manifest.json")
    if not os.path.exists(mpath):
        raise FileNotFoundError(f"manifest.json not found in {BP3D_EXPORT_DIR} (run export_bodyparts3d.py first)")
    with open(mpath, encoding="utf-8") as fh:
        man = json.load(fh)
    if man.get("schema") != 1:
        warn(f"unexpected manifest schema {man.get('schema')}")
    fr = man["frame"]
    log(f"manifest              : {len(man['structures'])} structures | mesh source: {man['dataset']['mesh_source']}")
    log(f"BP3D frame            : unit factor {fr['unit_factor_raw_to_mm']} | axes applied: {fr['applied']} | "
        f"confidence: {fr['confidence']} | output space: {fr['output_space']}")
    for m in fr.get("messages", []):
        warn(f"exporter: {m}")
    if not fr["applied"] or fr["confidence"] != "ok":
        warn("BodyParts3D anatomical frame was not established with high confidence; ICP will try to compensate "
             f"(limited to {REG_MAX_ROTATION_DEG} deg)")
    for m in man.get("missing", []):
        warn(f"not available in BodyParts3D export: {m}")
    for a in man.get("ambiguous", []):
        log(f"[ambiguous, not imported] {a['element']} {a['label']}")
    structs, rejected = [], []
    for s in man["structures"]:
        txt = f"{s['label']} {s['name']}".lower()
        if s.get("is_muscle") or MUSCLE_GUARD_RX.search(txt):
            rejected.append((s["name"], "muscle guard"))
            continue
        if CORTEX_GUARD_RX.search(s["label"].lower()) and not CORTEX_GUARD_EXCEPT_RX.search(s["label"].lower()):
            rejected.append((s["name"], "cerebral cortex duplicate guard"))
            continue
        path = os.path.join(BP3D_EXPORT_DIR, s["file"].replace("/", os.sep))
        if not os.path.exists(path):
            warn(f"missing mesh file for {s['name']}: {path}")
            continue
        v, f, _ = read_ply_binary(path)
        s = dict(s)
        s["verts"], s["faces"] = v, f
        structs.append(s)
    for n, why in rejected:
        warn(f"structure '{n}' rejected by {why}")
    log(f"structures loaded: {len(structs)}")
    ref = None
    if man["reference"].get("file"):
        rp = os.path.join(BP3D_EXPORT_DIR, man["reference"]["file"].replace("/", os.sep))
        if os.path.exists(rp):
            ref = np.load(rp)["points"].astype(np.float64)
            log(f"cortex reference cloud: {len(ref)} points from {man['reference']['elements']} elements "
                "(registration only, not imported)")
    if ref is None:
        warn("no BodyParts3D cortex reference cloud: registration falls back to landmarks")
    lm = {}
    for key, rxs in BP3D_LANDMARK_LABEL_RX.items():
        for hemi in ("L", "R"):
            vs = [s["verts"] for s in structs if s["side"] == hemi and re.search(rxs, s["label"].lower())]
            if vs:
                a = np.concatenate(vs)
                lm[f"{key}_{hemi}"] = (a.min(0) + a.max(0)) / 2.0
    log(f"BodyParts3D landmarks: {sorted(lm)}")
    return {"manifest": man, "structs": structs, "ref": ref, "landmarks": lm}


# ============================================================================
# REGISTRATION + PLACEMENT (numpy only)
# ============================================================================
# -----------------------------------------------------------------------------
# Compute the final placement transform for the integrated anatomical model.
# Parameters / return behavior: see the unchanged function signature and body.
# Combines registration results and anatomical extents to determine the model transform used in the scene.
# -----------------------------------------------------------------------------
def compute_placement(bn, bp):
    """Compute the final placement transform for the integrated anatomical model.

Combines registration results and anatomical extents to determine the model transform used in the scene."""
    log.section("Registration: Brainnetome cortex -> BodyParts3D")
    P = np.diag([-1.0, 1.0, 1.0]) if bn["frame"]["flip_x"] else np.eye(3)
    bn_lm = {k: P @ v for k, v in bn["landmarks"].items()}       # landmarks in RAS-corrected BN space
    bn_pts = np.concatenate([p["verts"] for p in bn["pieces"].values()]) @ P.T
    reg = None
    if bp["ref"] is not None:
        reg = register_cortex(bn_pts, bp["ref"])
        d = reg["diag"]
        log(f"BN cortex extent      : {np.round(d['bn_extent_mm'], 1).tolist()} mm")
        log(f"BP3D cortex extent    : {np.round(d['ref_extent_mm'], 1).tolist()} mm")
        log(f"per-axis size ratio   : {np.round(d['axis_ratios'], 3).tolist()}  (BP3D / BN)")
        log(f"initial (bbox) fit    : scale {d['initial']['scale']:.4f} | trimmed RMS {d['rms_initial_mm']:.2f} mm")
        if "icp" in d:
            ic = d["icp"]
            log(f"ICP                   : {ic['iterations']} it | scale {ic['scale']:.4f} | rot {ic['rotation_deg']:.2f} deg | "
                f"RMS {ic['rms_mm']:.2f} mm | {'ACCEPTED' if ic['accepted'] else 'REJECTED: ' + ic.get('rejected', '')}")
        log(f"method                : {reg['method']} | final trimmed RMS {d['rms_final_mm']:.2f} mm "
            f"(median {d['median_final_mm']:.2f} mm)")
    else:
        reg = register_landmarks(bn_lm, bp["landmarks"])
        if reg is None:
            raise RuntimeError("cannot register: neither a BodyParts3D cortex reference nor >= 4 matching "
                               "deep-structure landmarks are available")
        warn("registration from deep-structure landmarks only (LOW confidence)")
    s, R, t = reg["s"], reg["R"], reg["t"]
    if REG_MANUAL_SCALE:
        s = float(REG_MANUAL_SCALE)
        log(f"manual scale override : {s}")
    if any(REG_MANUAL_ROTATION_DEG):
        R = rot_from_euler_deg(*REG_MANUAL_ROTATION_DEG) @ R
    t = t + np.asarray(REG_MANUAL_TRANSLATION_MM, dtype=float)

    # ---- landmark validation (independent of the cortex-driven fit) ----
    res = landmark_residuals(bn_lm, bp["landmarks"], s, R, t)
    if res:
        rms = float(np.sqrt(np.mean(np.square(list(res.values())))))
        log(f"deep-structure landmark residuals after registration (BN vs BP3D centroids): RMS {rms:.2f} mm")
        for k, v in res.items():
            log(f"   {k:22s} {v:6.2f} mm")
        if rms > 12.0:
            warn(f"landmark RMS {rms:.1f} mm is large: the two datasets are only loosely compatible; "
                 "check the report and the manual override options")
    else:
        warn("no shared deep-structure landmarks: registration could not be validated independently")

    # ---- final frame: keep atlas orientation ----
    G = R.T if ORIENT_MODEL_TO_ATLAS else np.eye(3)
    A_bn = affine(1.0, G, np.zeros(3)) @ affine(s, R, t) @ affine(1.0, P, np.zeros(3))
    A_bp = affine(1.0, G, np.zeros(3))

    # ---- centering (mm) ----
    bn_all = apply_affine(A_bn, np.concatenate([p["verts"] for p in bn["pieces"].values()]))
    bp_all = apply_affine(A_bp, np.concatenate([st["verts"] for st in bp["structs"]])) if bp["structs"] else bn_all
    everything = np.concatenate([bn_all, bp_all])
    lo, hi = bbox(bn_all if CENTER_ON == "cortex_bbox" else everything)
    center = (lo + hi) / 2.0
    Cn = np.eye(4)
    Cn[:3, 3] = -center
    U = np.diag([BLENDER_UNITS_PER_MM] * 3 + [1.0])
    A_bn = U @ Cn @ A_bn
    A_bp = U @ Cn @ A_bp

    log.section("Registration result")
    ax, ang = axis_angle(R)
    log(f"BN -> BP3D scale factor          : {s:.5f}   (Brainnetome cortex enlarged/reduced by {100 * (s - 1):+.2f} %)")
    log(f"BN -> BP3D rotation (axis, deg)  : {np.round(ax, 4).tolist()} , {ang:.3f}   Euler XYZ {np.round(euler_from_rot_deg(R), 3).tolist()}")
    log(f"BN -> BP3D translation (mm)      : {np.round(t, 3).tolist()}")
    if ORIENT_MODEL_TO_ATLAS:
        log(f"whole model rotated back by       : {ang:.3f} deg (BodyParts3D anatomy is re-expressed in the atlas axes)")
    log(f"centering shift (mm)             : {np.round(-center, 3).tolist()}  (mode: {CENTER_ON})")
    log(f"mm -> Blender units              : {BLENDER_UNITS_PER_MM}")
    return {"reg": reg, "s": s, "R": R, "t": t, "P": P, "G": G, "A_bn": A_bn, "A_bp": A_bp,
            "landmark_residuals": res}


# ============================================================================
# BLENDER HELPERS
# ============================================================================
# -----------------------------------------------------------------------------
# Remove the previous generated anatomical model from the Blender scene.
# Parameters / return behavior: see the unchanged function signature and body.
# Clears the pipeline-owned collection/object hierarchy so the next build starts from a clean state.
# -----------------------------------------------------------------------------
def clear_previous_model():
    """Remove the previous generated anatomical model from the Blender scene.

Clears the pipeline-owned collection/object hierarchy so the next build starts from a clean state."""
    root = bpy.data.collections.get(ROOT_NAME)
    if root is not None:
        def walk(c):
            for ch in list(c.children):
                walk(ch)
            for o in list(c.objects):
                data = o.data
                bpy.data.objects.remove(o, do_unlink=True)
                if data is not None and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
            bpy.data.collections.remove(c)
        walk(root)
    for ob in [o for o in bpy.data.objects if o.name == ROOT_NAME]:
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in [m for m in bpy.data.materials if m.name.startswith(MATERIAL_PREFIX) and m.users == 0]:
        bpy.data.materials.remove(m)
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    txt = bpy.data.texts.get("ANATOMICAL_MODEL_REPORT")
    if txt is not None:
        bpy.data.texts.remove(txt)


# -----------------------------------------------------------------------------
# Create or prepare a Blender collection for generated anatomy.
# Parameters / return behavior: see the unchanged function signature and body.
# Returns the collection used to organize the generated anatomical objects.
# -----------------------------------------------------------------------------
def new_collection(name, parent):
    """Create or prepare a Blender collection for generated anatomy.

Returns the collection used to organize the generated anatomical objects."""
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


# -----------------------------------------------------------------------------
# Create the Blender material used by an anatomical structure.
# Parameters / return behavior: see the unchanged function signature and body.
# Builds and configures a material from the requested display properties.
# -----------------------------------------------------------------------------
def make_material(name, rgba, roughness=0.55):
    """Create the Blender material used by an anatomical structure.

Builds and configures a material from the requested display properties."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    except Exception as exc:                               # never fail the build because of shading
        log(f"[info] node material for {name} not created ({exc}); using viewport color only")
    mat.diffuse_color = rgba
    return mat


# -----------------------------------------------------------------------------
# Convert an sRGB color channel to linear color space.
# Parameters / return behavior: see the unchanged function signature and body.
# Applies the standard transfer function required for physically meaningful Blender color values.
# -----------------------------------------------------------------------------
def srgb_to_linear(c):
    """Convert an sRGB color channel to linear color space.

Applies the standard transfer function required for physically meaningful Blender color values."""
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c[:3]) + (1.0,)


# -----------------------------------------------------------------------------
# Create a Blender mesh object from numeric anatomical geometry.
# Parameters / return behavior: see the unchanged function signature and body.
# Builds mesh data, creates the object, assigns metadata/materials, and links it into the target collection.
# -----------------------------------------------------------------------------
def build_mesh_object(name, verts_final, faces, flip_faces, collection, material, parent):
    """verts_final: (N,3) already in final world coords. Origin set to the median (like the original importer)."""
    faces = faces[:, ::-1] if flip_faces else faces
    c = np.median(verts_final, axis=0)
    local = verts_final - c
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(local.astype(np.float32).tolist(), [], faces.astype(np.int64).tolist())
    mesh.update()
    mesh.validate()
    try:
        mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=bool))
    except Exception:
        pass
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = tuple(c.tolist())
    obj.parent = parent
    if material is not None:
        mesh.materials.append(material)
    return obj


# -----------------------------------------------------------------------------
# Scale an object around its own geometric center.
# Parameters / return behavior: see the unchanged function signature and body.
# Applies the requested scale while preserving the object center position.
# -----------------------------------------------------------------------------
def scale_about_own_center(verts, factor):
    """Scale an object around its own geometric center.

Applies the requested scale while preserving the object center position."""
    if factor == 1.0:
        return verts
    c = np.median(verts, axis=0)
    return c + (verts - c) * factor


# -----------------------------------------------------------------------------
# Resolve the display color assigned to a BodyParts3D structure.
# Parameters / return behavior: see the unchanged function signature and body.
# Maps the structure/group metadata to the configured anatomical color representation.
# -----------------------------------------------------------------------------
def bp3d_color(group, subgroup):
    """Resolve the display color assigned to a BodyParts3D structure.

Maps the structure/group metadata to the configured anatomical color representation."""
    return BP3D_COLORS.get((group, subgroup)) or BP3D_COLORS.get((group, None)) or (0.8, 0.8, 0.8, 1.0)


# ============================================================================
# SCENE ASSEMBLY
# ============================================================================
# -----------------------------------------------------------------------------
# Build the complete integrated Blender anatomical scene.
# Parameters / return behavior: see the unchanged function signature and body.
# Combines Brainnetome and BodyParts3D structures, applies placement, creates objects/materials, and organizes the final model collection.
# -----------------------------------------------------------------------------
def build_scene(bn, bp, place):
    """Build the complete integrated Blender anatomical scene.

Combines Brainnetome and BodyParts3D structures, applies placement, creates objects/materials, and organizes the final model collection."""
    log.section("Building the Blender scene")
    if CLEAR_PREVIOUS_MODEL:
        clear_previous_model()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "MILLIMETERS"

    root_coll = bpy.data.collections.new(ROOT_NAME)
    scene.collection.children.link(root_coll)
    brain_coll = new_collection("BRAIN", root_coll)
    spinal_coll = new_collection("SPINAL_SYSTEM", root_coll)
    help_coll = new_collection("HELPERS_METADATA", root_coll)
    systems = {"BRAIN": brain_coll, "SPINAL_SYSTEM": spinal_coll}
    cortex_coll = new_collection("CEREBRAL_CORTEX_BRAINNETOME", brain_coll)
    hemi_coll = {"L": new_collection("BN_LEFT_HEMISPHERE", cortex_coll),
                 "R": new_collection("BN_RIGHT_HEMISPHERE", cortex_coll),
                 "": cortex_coll}
    group_coll = {}

    root_obj = bpy.data.objects.new(ROOT_NAME, None)
    root_obj.empty_display_type = "PLAIN_AXES"
    root_obj.empty_display_size = 0.05
    help_coll.objects.link(root_obj)

    # ---------------- Brainnetome cortex ----------------
    A_bn = place["A_bn"]
    flip_bn = np.linalg.det(A_bn[:3, :3]) < 0
    n_bn = 0
    for rid in sorted(bn["pieces"]):
        p = bn["pieces"][rid]
        v = apply_affine(A_bn, p["verts"])
        v = scale_about_own_center(v, BN_REGION_GAP_SCALE)
        col = hemi_coll.get(p["hemi"], cortex_coll)
        mat = make_material(f"{MATERIAL_PREFIX}BN_{rid:03d}", srgb_to_linear(p["color"]))
        obj = build_mesh_object(f"BN_{rid:03d}_{safe_name(p['label'])}", v, p["faces"], flip_bn, col, mat, root_obj)
        obj["source"] = "Human Brainnetome"
        obj["bn_region_id"] = rid
        obj["bn_region_name"] = p["label"]
        obj["hemisphere"] = p["hemi"]
        n_bn += 1
    log(f"Brainnetome cortical regions created: {n_bn} (one object each)")

    # ---------------- BodyParts3D ----------------
    A_bp = place["A_bp"]
    flip_bp = np.linalg.det(A_bp[:3, :3]) < 0
    materials = {}
    counts = collections.Counter()
    for st in sorted(bp["structs"], key=lambda s: s["index"]):
        system, cname = GROUP_TO_COLLECTIONS.get(st["group"], ("SPINAL_SYSTEM", "OTHER_RELEVANT_STRUCTURES"))
        key = (system, cname)
        if key not in group_coll:
            group_coll[key] = new_collection(cname, systems[system])
        mk = (st["group"], st["subgroup"])
        if mk not in materials:
            rgba = bp3d_color(*mk)
            materials[mk] = make_material(f"{MATERIAL_PREFIX}BP3D_{st['group']}_{st['subgroup'] or 'all'}", rgba)
        v = apply_affine(A_bp, st["verts"])
        obj = build_mesh_object(st["name"], v, st["faces"], flip_bp, group_coll[key], materials[mk], root_obj)
        obj["source"] = "BodyParts3D"
        obj["bp3d_group"] = st["group"]
        obj["bp3d_subgroup"] = st["subgroup"]
        obj["bp3d_elements"] = ",".join(st["elements"])
        obj["bp3d_concepts"] = ",".join(st["concepts"])
        counts[st["group"]] += 1
    for g, n in sorted(counts.items()):
        log(f"BodyParts3D {g:26s}: {n}")

    # ---------------- helpers: landmark empties ----------------
    for k, v in sorted(bp["landmarks"].items()):
        e = bpy.data.objects.new(f"LM_BP3D_{k}", None)
        e.empty_display_type, e.empty_display_size = "SPHERE", 3.0 * BLENDER_UNITS_PER_MM
        e.location = tuple(apply_affine(A_bp, v[None, :])[0].tolist())
        help_coll.objects.link(e)
        e.hide_viewport = True
    for k, v in sorted(bn["landmarks"].items()):
        e = bpy.data.objects.new(f"LM_BN_{k}", None)
        e.empty_display_type, e.empty_display_size = "CUBE", 3.0 * BLENDER_UNITS_PER_MM
        e.location = tuple(apply_affine(A_bn, v[None, :])[0].tolist())   # A_bn already contains the x-flip
        help_coll.objects.link(e)
        e.hide_viewport = True
    return root_obj, root_coll, help_coll


# -----------------------------------------------------------------------------
# Return generated anatomical objects belonging to the model collection.
# Parameters / return behavior: see the unchanged function signature and body.
# Traverses the generated collection and yields the objects that represent anatomical structures.
# -----------------------------------------------------------------------------
def model_objects(root_coll):
    """Return generated anatomical objects belonging to the model collection.

Traverses the generated collection and yields the objects that represent anatomical structures."""
    out = []

    def walk(c):
        out.extend(c.objects)
        for ch in c.children:
            walk(ch)
    walk(root_coll)
    return out


# -----------------------------------------------------------------------------
# Audit the generated Blender scene for expected model integrity.
# Parameters / return behavior: see the unchanged function signature and body.
# Checks object counts, metadata, collections, and other structural conditions after scene construction.
# -----------------------------------------------------------------------------
def audit_scene(root_coll):
    """Audit the generated Blender scene for expected model integrity.

Checks object counts, metadata, collections, and other structural conditions after scene construction."""
    log.section("Final audit")
    objs = [o for o in model_objects(root_coll) if o.type == "MESH"]
    bad = [o.name for o in objs if MUSCLE_GUARD_RX.search(o.name.lower()) or
           MUSCLE_GUARD_RX.search(str(o.get("bp3d_concepts", "")).lower())]
    log(f"mesh objects in model: {len(objs)} | muscle objects: {len(bad)}")
    if bad:
        raise RuntimeError(f"muscle objects found in the scene: {bad}")
    dup_cortex = [o.name for o in objs if o.get("source") == "BodyParts3D" and
                  CORTEX_GUARD_RX.search(o.name.lower()) and not CORTEX_GUARD_EXCEPT_RX.search(o.name.lower())]
    log(f"BodyParts3D cortical duplicates: {len(dup_cortex)}")
    if dup_cortex:
        raise RuntimeError(f"cerebral cortex duplicates present: {dup_cortex}")
    names = [o.name for o in bpy.data.objects]
    if len(names) != len(set(names)):
        warn("duplicate object names detected")
    tri = sum(len(o.data.polygons) for o in objs)
    log(f"total faces: {tri}")
    return objs


# -----------------------------------------------------------------------------
# Generate geometric statistics for the integrated model.
# Parameters / return behavior: see the unchanged function signature and body.
# Computes bounds and structure-level geometry information used for validation and reporting.
# -----------------------------------------------------------------------------
def geometry_report(bn, bp, place):
    """Generate geometric statistics for the integrated model.

Computes bounds and structure-level geometry information used for validation and reporting."""
    log.section("Anatomical relationship checks (final model space, mm)")
    mm = 1.0 / BLENDER_UNITS_PER_MM
    invU = np.diag([mm, mm, mm, 1.0])
    A_bn = invU @ place["A_bn"]
    A_bp = invU @ place["A_bp"]
    bn_all = apply_affine(A_bn, np.concatenate([p["verts"] for p in bn["pieces"].values()]))
    lo, hi = bbox(bn_all)
    log(f"Brainnetome cortex bbox: {np.round(lo, 1).tolist()} .. {np.round(hi, 1).tolist()}")
    groups = collections.defaultdict(list)
    for st in bp["structs"]:
        groups[st["group"]].append(apply_affine(A_bp, st["verts"]))
    cat = {g: np.concatenate(v) for g, v in groups.items()}
    if "CEREBELLUM" in cat:
        c = cat["CEREBELLUM"]
        inside = np.all((c >= lo) & (c <= hi), axis=1).mean()
        log(f"cerebellum vertices inside the cortex bbox: {100 * inside:.1f} % "
            f"(cerebellum top z = {c[:, 2].max():.1f} mm vs cortex bottom z = {lo[2]:.1f} mm)")
    if "SUBCORTICAL_STRUCTURES" in cat:
        c = cat["SUBCORTICAL_STRUCTURES"]
        inside = np.all((c >= lo) & (c <= hi), axis=1).mean()
        log(f"deep structure vertices inside the cortex bbox: {100 * inside:.1f} %")
        if inside < 0.9:
            warn("less than 90 % of the subcortical vertices lie inside the Brainnetome cortex bbox")
    if "BRAINSTEM" in cat and "SPINAL_CORD" in cat:
        zb, zc = cat["BRAINSTEM"][:, 2].min(), cat["SPINAL_CORD"][:, 2].max()
        log(f"brainstem lowest z {zb:.1f} | spinal cord highest z {zc:.1f} | gap {zb - zc:+.1f} mm "
            f"({'overlap = continuous' if zb - zc <= 0 else 'gap'})")
        if zb - zc > 5.0:
            warn(f"brainstem and spinal cord are separated by {zb - zc:.1f} mm in the source data")
    if "SPINAL_CORD" in cat and "VERTEBRAE" in cat:
        cd, vt = cat["SPINAL_CORD"], cat["VERTEBRAE"]
        log(f"cord centre x/y = ({cd[:, 0].mean():+.1f}, {cd[:, 1].mean():+.1f}) mm | vertebral column centre x/y = "
            f"({vt[:, 0].mean():+.1f}, {vt[:, 1].mean():+.1f}) mm")
        cy_lo, cy_hi = vt[:, 1].min(), vt[:, 1].max()
        if not (cy_lo <= cd[:, 1].mean() <= cy_hi):
            warn("spinal cord is not within the anterior-posterior extent of the vertebral column")
    if "INTERVERTEBRAL_DISCS" in cat and "VERTEBRAE" in cat:
        vz = [apply_affine(A_bp, st["verts"])[:, 2].mean() for st in bp["structs"] if st["group"] == "VERTEBRAE"]
        dz = [apply_affine(A_bp, st["verts"])[:, 2].mean() for st in bp["structs"]
              if st["group"] == "INTERVERTEBRAL_DISCS"]
        log(f"vertebral centres z: {min(vz):.1f} .. {max(vz):.1f} mm | disc centres z: {min(dz):.1f} .. {max(dz):.1f} mm")


# -----------------------------------------------------------------------------
# Write the final integration report and summary information.
# Parameters / return behavior: see the unchanged function signature and body.
# Combines pipeline statistics, registration results, and scene validation information into the final report.
# -----------------------------------------------------------------------------
def final_report(root_obj, root_coll, place, bn, bp):
    """Write the final integration report and summary information.

Combines pipeline statistics, registration results, and scene validation information into the final report."""
    log.section("Final model")
    bpy.context.view_layer.update()
    objs = [o for o in model_objects(root_coll) if o.type == "MESH"]
    pts = []
    for o in objs:
        mw = np.array(o.matrix_world)
        co = np.empty(len(o.data.vertices) * 3, dtype=np.float32)
        o.data.vertices.foreach_get("co", co)
        pts.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
    allp = np.concatenate(pts)
    lo, hi = bbox(allp)
    dims = hi - lo
    log(f"final bounding box (Blender units, 1 unit = {1 / BLENDER_UNITS_PER_MM / 1000:.3f} m): "
        f"{np.round(lo, 4).tolist()} .. {np.round(hi, 4).tolist()}")
    log(f"final dimensions (mm): {np.round(dims / BLENDER_UNITS_PER_MM, 1).tolist()}")
    log(f"final center (Blender units): {np.round((lo + hi) / 2, 5).tolist()}")
    log(f"final scale factors: BN->BP3D {place['s']:.5f} | mm->Blender {BLENDER_UNITS_PER_MM} | "
        f"object transforms: identity rotation/scale, origin at each piece median")
    root_obj["registration_json"] = json.dumps({
        "bn_to_bp3d_scale": place["s"], "rotation_matrix": place["R"].tolist(),
        "translation_mm": place["t"].tolist(), "method": place["reg"]["method"],
        "orient_model_to_atlas": ORIENT_MODEL_TO_ATLAS, "units_per_mm": BLENDER_UNITS_PER_MM,
        "landmark_residuals_mm": place["landmark_residuals"]})
    log.section("Warnings")
    for w in WARNINGS:
        log(f"- {w}")
    if not WARNINGS:
        log("none")
    txt = bpy.data.texts.new("ANATOMICAL_MODEL_REPORT")
    txt.write("\n".join(log.lines))


# -----------------------------------------------------------------------------
# Apply the pipeline viewport setup used for the generated anatomical scene.
# Parameters / return behavior: see the unchanged function signature and body.
# Configures the Blender viewport state required by the existing pipeline without changing anatomical geometry.
# -----------------------------------------------------------------------------
def setup_viewport():
    """Apply the pipeline viewport setup used for the generated anatomical scene.

Configures the Blender viewport state required by the existing pipeline without changing anatomical geometry."""
    if not SET_SOLID_MATERIAL_VIEWPORT:
        return
    try:
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                sp = area.spaces.active
                sp.shading.type = "MATERIAL"
                sp.clip_start = 0.001
                sp.clip_end = 100.0
    except Exception:
        pass


# ============================================================================
# MAIN
# ============================================================================
# -----------------------------------------------------------------------------
# Run the complete Brainnetome + BodyParts3D integration pipeline.
# Parameters / return behavior: see the unchanged function signature and body.
# Loads both anatomical sources, registers them, builds the Blender scene, audits the result, and writes the final report.
# -----------------------------------------------------------------------------
def main():
    """Run the complete Brainnetome + BodyParts3D integration pipeline.

Loads both anatomical sources, registers them, builds the Blender scene, audits the result, and writes the final report."""
    log.section("Brainnetome + BodyParts3D integration")
    bn = load_brainnetome()
    bp = load_bodyparts3d()
    place = compute_placement(bn, bp)
    root_obj, root_coll, _ = build_scene(bn, bp, place)
    audit_scene(root_coll)
    geometry_report(bn, bp, place)
    final_report(root_obj, root_coll, place, bn, bp)
    setup_viewport()
    log("\nDone. Full report: Text Editor -> ANATOMICAL_MODEL_REPORT (also stored on the root empty).")


if __name__ == "__main__":
    main()
"""Dataset loading, validation, and final placement calculation.

Function implementations are preserved from the original single-file script.
"""
import os
import re
import json
import math
import collections
import numpy as np
from medverse.integration.config import *
from medverse.integration.geometry import *

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

"""
anat_helpers.py
---------------
Every stand-alone helper FUNCTION used by the two pipelines (no classes here).

Sections
    1. generic        : names, bbox, rotations, similarity maths, nearest neighbour
    2. file I/O       : PLY / OBJ / LUT / metadata TSV
    3. BodyParts3D    : classification, mesh cleaning, decimation, frame inference
    4. registration   : cortex ICP, landmark registration
    5. Blender        : scene / material / mesh builders   (need bpy; harmless to import without it)

Works in plain Python (export) AND inside Blender (integrate).
scipy is imported lazily inside clean_mesh() because Blender does not ship it.
"""
import os
import re
import math
import collections
import numpy as np
from medverse.anatomy.config import *  # noqa: F401,F403

try:                            # Blender only
    import bpy
except ImportError:
    bpy = None

try:                            # optional decimation (export only)
    import fast_simplification
except ImportError:
    fast_simplification = None


# ============================================================================
# 1. GENERIC
# ============================================================================
def sanitize(s):
    """Filesystem-safe identifier (spaces -> underscore)."""
    return "".join(c if (c.isalnum() or c in "_-") else "_" for c in s.strip().replace(" ", "_")).strip("_")


def safe_name(name):
    """Blender / filesystem safe name (drops every other character)."""
    return "".join(c for c in name if c.isalnum() or c in "_-")


def bbox(points):
    """Axis-aligned bounding box -> (min, max)."""
    return points.min(0), points.max(0)


def rot_angle_deg(R):
    """Rotation angle (deg) of a rotation matrix."""
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0))))


def rot_from_euler_deg(rx, ry, rz):
    """Rotation matrix from XYZ Euler angles in degrees (Rz @ Ry @ Rx)."""
    a, b, c = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def euler_from_rot_deg(R):
    """XYZ Euler angles (deg) of a rotation matrix."""
    sy = math.hypot(R[0, 0], R[1, 0])
    if sy > 1e-9:
        x, y, z = math.atan2(R[2, 1], R[2, 2]), math.atan2(-R[2, 0], sy), math.atan2(R[1, 0], R[0, 0])
    else:
        x, y, z = math.atan2(-R[1, 2], R[1, 1]), math.atan2(-R[2, 0], sy), 0.0
    return tuple(float(np.degrees(v)) for v in (x, y, z))


def axis_angle(R):
    """Rotation matrix -> ((ax, ay, az), angle_deg)."""
    ang = rot_angle_deg(R)
    if ang < 1e-6:
        return (0.0, 0.0, 1.0), 0.0
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(ax)
    return (tuple((ax / n).tolist()) if n > 1e-12 else (0.0, 0.0, 1.0)), ang


def umeyama(src, dst, fix_scale=None):
    """Least-squares similarity  dst ~ s * R @ src + t  (R proper rotation)."""
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


def stride_sample(points, n):
    """Deterministic down-sampling by striding."""
    if len(points) <= n:
        return points
    return points[np.linspace(0, len(points) - 1, n).astype(np.int64)]


def apply_sim(points, s, R, t):
    """s * R @ p + t for every point."""
    return s * (points @ R.T) + t


def affine(s, R, t):
    """4x4 matrix of the similarity (s, R, t)."""
    A = np.eye(4)
    A[:3, :3] = s * R
    A[:3, 3] = t
    return A


def apply_affine(A, pts):
    """Apply a 4x4 affine matrix to (N,3) points."""
    return pts @ A[:3, :3].T + A[:3, 3]


def trimmed_rms(ref, moving, trim):
    """(trimmed RMS, median) of nearest-neighbour distances ref -> moving."""
    _, d = nearest(ref, moving)
    keep = d <= np.quantile(d, trim)
    return float(np.sqrt((d[keep] ** 2).mean())), float(np.median(d))


def _unit(v):
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("degenerate direction")
    return v / n


def _angle(a, b):
    return float(np.degrees(np.arccos(np.clip(np.dot(_unit(a), _unit(b)), -1, 1))))


# ============================================================================
# 2. FILE I/O
# ============================================================================
_PLY_TYPES = {"char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1", "short": "<i2", "ushort": "<u2",
              "int16": "<i2", "uint16": "<u2", "int": "<i4", "uint": "<u4", "int32": "<i4", "uint32": "<u4",
              "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8"}


def read_ply_binary(path):
    """Read a binary_little_endian triangle PLY.
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
        else:
            raise ValueError(f"unsupported PLY element '{el['name']}'")
    if verts is None or faces is None:
        raise ValueError("PLY has no vertex/face element")
    return verts, faces, rgb


def write_ply_binary(path, verts, faces):
    """Write a triangle mesh as binary_little_endian PLY."""
    v = np.empty(len(verts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")])
    v["x"], v["y"], v["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    f = np.empty(len(faces), dtype=[("n", "u1"), ("idx", "<i4", (3,))])
    f["n"] = 3
    f["idx"] = faces
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(v)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              f"element face {len(f)}\n"
              "property list uchar int vertex_indices\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.tobytes())
        fh.write(f.tobytes())


def read_obj(path):
    """Read an OBJ (v / f only); n-gons are fan-triangulated."""
    verts, faces = [], []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    i = int(tok.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise ValueError(f"face index out of range in {path}")
    return v, f


def read_lut(path):
    """FreeSurfer style LUT: index name R G B A  ->  {id: (name, (r,g,b))}."""
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


def find_metadata_files(base, override_dir):
    """Locate the six BodyParts3D metadata .txt files -> {key: path}."""
    root = override_dir or base
    found = {}
    if not os.path.isdir(root):
        raise FileNotFoundError(f"metadata search folder does not exist: {root}")
    all_files = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.lower().endswith(".txt"):
                all_files.append(os.path.join(dp, fn))
    for key, suffix in METADATA_SUFFIXES.items():
        cands = sorted((p for p in all_files if os.path.basename(p).lower().endswith(suffix)),
                       key=lambda p: (len(p), p))
        if not cands:
            raise FileNotFoundError(f"metadata file '*{suffix}' not found under {root}")
        found[key] = cands[0]
    return found


def read_tsv(path, min_cols):
    """Tab-separated metadata file -> (header, rows)."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        lines = [l.rstrip("\r\n") for l in fh]
    rows = []
    for l in lines[1:]:
        if not l.strip():
            continue
        p = [x.strip() for x in l.split("\t")]
        if len(p) >= min_cols:
            rows.append(p)
    return lines[0].split("\t") if lines else [], rows


# ============================================================================
# 3. BODYPARTS3D: naming, classification, geometry, frame inference
# ============================================================================
def side_from_names(names):
    """'L' / 'R' / '' from a set of concept names."""
    left = any(re.search(r"\bleft\b", n) for n in names)
    right = any(re.search(r"\bright\b", n) for n in names)
    if left and not right:
        return "L"
    if right and not left:
        return "R"
    return ""


def spine_code(label):
    """'tenth thoracic vertebra' -> 'T10' | 'atlas' -> 'C1' | 'axis' -> 'C2' ; '' if unknown."""
    l = label.lower()
    if l == "atlas":
        return "C1"
    if l == "axis" or l.endswith(" of axis"):
        return "C2"
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\b", l):
            if "cervical" in l:
                return f"C{n}"
            if "thoracic" in l:
                return f"T{n}"
            if "lumbar" in l:
                return f"L{n}"
    if l == "sacrum":
        return "S"
    return ""


def code_order(code):
    """Sortable key for vertebral codes."""
    if not code:
        return (9, 0)
    return ({"C": 0, "T": 1, "L": 2, "S": 3}[code[0]], int(code[1:] or 0))


def compute_muscle_elements(meta):
    """Union of (a) all elements of the isa 'muscle organ' subtree, (b) name-rule hits."""
    muscle = set()
    for cid in meta.concepts_by_name(exact="muscle organ"):
        muscle |= meta.subtree_elements("isa", cid)
        muscle |= meta.elements["isa"].get(cid, set())
    n_tree = len(muscle)
    for fj in meta.all_fjs:
        if fj in muscle:
            continue
        if any(MUSCLE_NAME_RX.search(n) for n in meta.names_of(fj)):
            muscle.add(fj)
    return muscle, n_tree


def _whitelisted(names):
    return any(re.search(p, n) for p in AMBIGUOUS_INCLUDE_PATTERNS for n in names)


def classify_all(meta, muscle):
    """Return dict fj -> decision record for every element that is in a requested scope."""
    cord_fj = set()
    for cid in meta.concepts_by_name(exact="spinal cord"):
        cord_fj |= meta.elements["partof"].get(cid, set())
    spine_fj = set()
    for cid in meta.concepts_by_name(exact="vertebral column"):
        spine_fj |= meta.subtree_elements("partof", cid) | meta.elements["partof"].get(cid, set())
    brain_fj = set()
    for cid in meta.concepts_by_name(exact="brain"):
        brain_fj |= meta.elements["partof"].get(cid, set())
    for fj in meta.all_fjs:
        names = meta.names_of(fj)
        own = {meta.name[c].lower() for _, c in meta.own_concepts(fj)}
        if any(BRAIN_SCOPE_RX.search(n) for n in names) and not any(VESSEL_RX.search(n) for n in own):
            brain_fj.add(fj)
    adjacent_fj = {fj for fj in meta.all_fjs if any(ADJACENT_RX.search(n) for n in meta.names_of(fj))}

    out = {}
    for fj in sorted(cord_fj | spine_fj | brain_fj | adjacent_fj):
        names = meta.names_of(fj)
        own_c = meta.own_concepts(fj)
        own = sorted({meta.name[c].lower() for _, c in own_c})
        label = meta.label_of(fj)
        rec = {"fj": fj, "names": sorted(names), "own_names": own, "label": label,
               "concepts": sorted({c for _, c in own_c}), "decision": "exclude", "group": None,
               "subgroup": "", "reason": "", "notes": []}
        out[fj] = rec

        if fj in muscle:
            rec["reason"] = "muscle"
            continue
        if fj in cord_fj:
            rec.update(decision="include", group="SPINAL_CORD", subgroup="spinal_cord",
                       label="spinal cord", reason="concept 'spinal cord' element")
            if any("central canal" in n for n in names):
                rec["notes"].append("same element file is also registered as 'central canal of spinal cord' "
                                    "in the metadata; verified by geometry in the report")
            continue
        if fj in spine_fj:
            if any(DISC_RX.search(n) for n in names):
                rec.update(decision="include", group="INTERVERTEBRAL_DISCS", subgroup="disc",
                           reason="intervertebral disk concept")
                rec["label"] = next((n for n in own if DISC_RX.search(n)), label)
            elif any(SACRUM_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="sacral", label="sacrum",
                           reason="sacrum")
            elif any(COCCYX_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="coccygeal", reason="coccyx")
            elif any(CERVICAL_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="cervical", reason="cervical vertebra")
            elif any(THORACIC_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="thoracic", reason="thoracic vertebra")
            elif any(LUMBAR_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="lumbar", reason="lumbar vertebra")
            else:
                rec.update(decision="ambiguous", reason="element of vertebral column not recognised by name rules")
            continue
        if fj in adjacent_fj and fj not in brain_fj:
            rec.update(decision="ambiguous", reason="non-CNS structure attached to the brain "
                       "(optic chiasm / pituitary / tentorium); excluded unless whitelisted")
            if _whitelisted(names):
                rec["decision"] = "include"
                rec.update(group="OTHER_BRAIN_STRUCTURES", subgroup="adjacent")
            continue
        # ---------------- brain scope ----------------
        if any(HIPPOCAMPUS_RX.search(n) for n in own):
            rec.update(decision="ambiguous", reason="hippocampus: filed by BodyParts3D under 'region of "
                       "cerebral cortex' but Brainnetome treats it as subcortical")
            if _whitelisted(own):
                rec.update(decision="include", group="SUBCORTICAL_STRUCTURES", subgroup="hippocampus")
            continue
        if any(CORTEX_RX.search(n) for n in names):
            rec.update(decision="exclude", group="CORTEX_DUPLICATE", reason="cerebral cortex -> Brainnetome")
            continue
        if any(VENTRICLE_RX.search(n) for n in names):
            rec.update(decision="include" if INCLUDE_VENTRICULAR_SYSTEM else "exclude",
                       group="OTHER_BRAIN_STRUCTURES", subgroup="ventricular_system",
                       reason="ventricular system" + ("" if INCLUDE_VENTRICULAR_SYSTEM else " (disabled)"))
            continue
        if any(CEREBELLUM_RX.search(n) for n in names):
            rec.update(decision="include", group="CEREBELLUM", subgroup="cerebellum", reason="cerebellum")
            continue
        if any(BRAINSTEM_RX.search(n) for n in names):
            sub = "midbrain"
            if any(n in ("pons",) for n in names):
                sub = "pons"
            elif any(n == "medulla oblongata" for n in names):
                sub = "medulla_oblongata"
            rec.update(decision="include", group="BRAINSTEM", subgroup=sub, reason="brainstem part")
            continue
        if any(SUBCORTICAL_RX.search(n) for n in names):
            rec.update(decision="include", group="SUBCORTICAL_STRUCTURES", subgroup="deep_gray_matter",
                       reason="diencephalon / basal ganglia / amygdala")
            continue
        if any(WHITE_MATTER_RX.search(n) for n in names):
            rec.update(decision="include" if INCLUDE_CEREBRAL_WHITE_MATTER else "exclude",
                       group="OTHER_BRAIN_STRUCTURES", subgroup="white_matter",
                       reason="deep white matter" + ("" if INCLUDE_CEREBRAL_WHITE_MATTER else " (disabled)"))
            continue
        rec.update(decision="ambiguous", reason="in brain scope but matches no rule")

    if INCLUDE_CRANIAL_NERVES:
        for fj in meta.all_fjs:
            if fj in out or fj in muscle:
                continue
            if any(NERVE_RX.search(n) for n in meta.names_of(fj)):
                own = sorted({meta.name[c].lower() for _, c in meta.own_concepts(fj)})
                out[fj] = {"fj": fj, "names": sorted(meta.names_of(fj)), "own_names": own, "label": meta.label_of(fj),
                           "concepts": sorted({c for _, c in meta.own_concepts(fj)}), "decision": "include",
                           "group": "CRANIAL_NERVES", "subgroup": "cranial_nerve",
                           "reason": "nerve (INCLUDE_CRANIAL_NERVES)", "notes": []}
    return out


def build_units(meta, fj_records, mesh_mode):
    """Group elements into mesh 'units' (1 element or 1 concept representation). -> (units, problems)"""
    units = []
    if mesh_mode == "element":
        for rec in fj_records:
            units.append({"key": rec["fj"], "fjs": [rec["fj"]], "stems": [rec["fj"]], "hint": "",
                          "recs": [rec], "concept": rec["concepts"][0] if rec["concepts"] else ""})
        return units, []
    chosen = {}
    problems = []
    sel = {r["fj"] for r in fj_records}
    for rec in fj_records:
        tc = meta.own_concepts(rec["fj"])[0]
        chosen.setdefault(tc, []).append(rec)
    for (tree, cid), recs in sorted(chosen.items(), key=lambda kv: kv[0][1]):
        elems = meta.elements[tree][cid]
        bp = meta.rep[tree].get(cid)
        if not bp:
            problems.append(f"{cid} {meta.name[cid]}: no representation id (BP) in {tree}_parts_list_e.txt")
            continue
        if not elems <= sel:
            problems.append(f"{cid} {meta.name[cid]}: concept mesh also contains unselected elements "
                            f"({len(elems - sel)}); skipped to avoid importing excluded anatomy")
            continue
        units.append({"key": bp, "fjs": sorted(elems), "stems": [bp], "hint": tree, "recs": recs,
                      "concept": cid})
    return units, problems


# ---------------------------------------------------------------- mesh cleaning
def signed_volume(v, f):
    """Signed volume of a closed triangle mesh."""
    if len(f) == 0:
        return 0.0
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def is_closed(f):
    """True when every edge is shared by exactly two faces."""
    if len(f) == 0:
        return False
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e.sort(axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def clean_mesh(verts, faces, weld_tol):
    """Weld, drop degenerate/duplicate faces, drop tiny islands, fix inverted closed meshes."""
    from scipy.sparse import coo_matrix                      # lazy: Blender has no scipy
    from scipy.sparse.csgraph import connected_components

    stats = {"raw_verts": len(verts), "raw_faces": len(faces)}
    q = np.round(verts / weld_tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    verts = verts[first]
    faces = inv.reshape(-1)[faces]
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    stats["degenerate"] = int((~ok).sum())
    faces = faces[ok]
    key = np.sort(faces, axis=1)
    _, keep = np.unique(key, axis=0, return_index=True)
    stats["duplicate"] = int(len(faces) - len(keep))
    faces = faces[np.sort(keep)]
    n = len(verts)
    if len(faces):
        a = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
        b = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
        g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
        ncomp, lab = connected_components(g, directed=False)
        fcount = np.bincount(lab[faces[:, 0]], minlength=ncomp)
        tot = fcount.sum()
        small = (fcount < COMPONENT_MIN_FACES) & (fcount < COMPONENT_MIN_FRACTION * tot)
        if small.all():
            small[np.argmax(fcount)] = False
        stats["components"] = int(ncomp)
        stats["islands_removed"] = int(small.sum())
        faces = faces[~small[lab[faces[:, 0]]]]
    else:
        stats["components"], stats["islands_removed"] = 0, 0
    used = np.unique(faces)
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    verts, faces = verts[used], remap[faces]
    vol = signed_volume(verts, faces)
    stats["closed"] = is_closed(faces)
    stats["flipped"] = False
    if stats["closed"] and vol < 0:
        faces = faces[:, ::-1].copy()
        stats["flipped"] = True
        vol = -vol
    stats["volume_raw"] = float(vol)
    return verts, faces, stats


def decimate(verts, faces, budget):
    """Optional fast_simplification decimation. -> (verts, faces, decimated?, note)"""
    if fast_simplification is None or len(faces) <= budget:
        return verts, faces, False, ""
    red = 1.0 - budget / float(len(faces))
    try:
        v2, f2 = fast_simplification.simplify(verts.astype(np.float64), faces.astype(np.int64),
                                              target_reduction=red, agg=DECIMATION_AGGRESSIVENESS)
    except Exception as exc:
        return verts, faces, False, f"decimation failed ({exc})"
    drift = max(np.abs(v2.min(0) - verts.min(0)).max(), np.abs(v2.max(0) - verts.max(0)).max())
    if drift > MAX_BBOX_DRIFT_MM:
        return verts, faces, False, f"decimation rejected (bbox drift {drift:.2f})"
    return v2, f2.astype(np.int64), True, ""


# ---------------------------------------------------------------- frame inference
def infer_frame(units):
    """
    units: list of dict(points=Nx3 raw, group, subgroup, side, names, cortex(bool)).
    Returns dict describing the raw -> RAS(mm) transform, with diagnostics.
    """
    info = {"applied": False, "confidence": "none", "messages": []}

    def pts(sel):
        arr = [u["points"] for u in units if sel(u)]
        return np.concatenate(arr) if arr else np.empty((0, 3))

    vert = pts(lambda u: u["group"] == "VERTEBRAE")
    factor = 1.0
    if len(vert) > 100:
        c = vert.mean(0)
        _, _, vt = np.linalg.svd(vert - c, full_matrices=False)
        proj = (vert - c) @ vt[0]
        length = float(proj.max() - proj.min())
        lo, hi = VERTEBRAL_COLUMN_LENGTH_RANGE_MM
        fits = [f for f in UNIT_CANDIDATE_FACTORS if lo <= length * f <= hi]
        info["vertebral_length_raw"] = length
        if len(fits) == 1:
            factor = fits[0]
        else:
            info["messages"].append(f"unit factor ambiguous/undetermined (length {length:.3f}, candidates {fits}); "
                                    "assuming 1.0 (millimetres)")
    else:
        info["messages"].append("no vertebrae available to infer units; assuming millimetres")
    info["unit_factor_to_mm"] = factor

    brain_all = pts(lambda u: u["group"] in ("CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES",
                                              "OTHER_BRAIN_STRUCTURES") or u["cortex"])
    low_spine = pts(lambda u: u["group"] == "VERTEBRAE" and u["subgroup"] in ("lumbar", "sacral"))
    cord = pts(lambda u: u["group"] == "SPINAL_CORD")
    left = pts(lambda u: u["side"] == "L" and (u["cortex"] or u["group"] in ("SUBCORTICAL_STRUCTURES",)))
    right = pts(lambda u: u["side"] == "R" and (u["cortex"] or u["group"] in ("SUBCORTICAL_STRUCTURES",)))
    frontal = pts(lambda u: u["cortex"] and any(re.search(r"frontal", n) and not re.search(r"nerve", n)
                                                 for n in u["names"]))
    occip = pts(lambda u: u["cortex"] and any("occipital" in n for n in u["names"]))
    cereb = pts(lambda u: u["group"] == "CEREBELLUM")
    bstem = pts(lambda u: u["group"] == "BRAINSTEM")

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
        A_cands = []
        if len(frontal) and len(occip):
            A_cands.append(_unit(frontal.mean(0) - occip.mean(0)))
        if len(cereb) and len(bstem):
            A_cands.append(_unit(bstem.mean(0) - cereb.mean(0)))
        if not A_cands:
            raise ValueError("no anterior-posterior landmarks")
        A = _unit(np.sum(A_cands, axis=0))
        angs = {"R-S": _angle(R, S), "A-S": _angle(A, S), "R-A": _angle(R, A)}
        info["raw_axis_angles_deg"] = angs
        worst = max(abs(90.0 - a) for a in angs.values())
        Rn = _unit(R - S * np.dot(R, S))
        An = _unit(A - S * np.dot(A, S) - Rn * np.dot(A, Rn))
        M = np.vstack([Rn, An, S])
        info["matrix_raw_to_ras"] = M.tolist()
        info["determinant"] = float(np.linalg.det(M))
        info["applied"] = True
        info["confidence"] = "ok" if worst <= AXIS_ORTHOGONALITY_TOLERANCE_DEG else "low"
        info["worst_orthogonality_error_deg"] = worst
        if len(A_cands) == 2:
            info["ap_landmark_disagreement_deg"] = _angle(A_cands[0], A_cands[1])
        if info["determinant"] < 0:
            info["messages"].append("raw frame is mirrored with respect to the anatomical labels "
                                    "(left/right); faces will be flipped")
        if info["confidence"] == "low":
            info["messages"].append(f"axes are only {90 - worst:.0f}..90 deg orthogonal: LOW confidence")
    except ValueError as exc:
        info["messages"].append(f"axis inference failed: {exc}; raw orientation kept")
        info["matrix_raw_to_ras"] = np.eye(3).tolist()
        info["determinant"] = 1.0
    return info


# ============================================================================
# 4. REGISTRATION  (Brainnetome <-> BodyParts3D)
# ============================================================================
def register_cortex(bn_pts, ref_pts):
    """Returns dict(s, R, t, method, diag). Maps BN (MNI mm) -> BP3D space (mm)."""
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


def register_landmarks(bn_lm, bp_lm, fixed_scale=None):
    """Similarity from matching deep-structure landmarks (needs >= 4)."""
    keys = sorted(set(bn_lm) & set(bp_lm))
    if len(keys) < 4:
        return None
    src = np.array([bn_lm[k] for k in keys])
    dst = np.array([bp_lm[k] for k in keys])
    s, R, t = umeyama(src, dst, fix_scale=fixed_scale)
    return {"s": s, "R": R, "t": t, "method": "landmarks", "keys": keys, "diag": {}}


def landmark_residuals(bn_lm, bp_lm, s, R, t):
    """Per-landmark distance (mm) between the transformed BN landmark and the BP3D landmark."""
    out = {}
    for k in sorted(set(bn_lm) & set(bp_lm)):
        p = apply_sim(np.asarray(bn_lm[k])[None, :], s, R, t)[0]
        out[k] = float(np.linalg.norm(p - np.asarray(bp_lm[k])))
    return out


# ============================================================================
# 5. BLENDER HELPERS  (bpy required when called)
# ============================================================================
def clear_previous_model():
    """Remove an earlier ANATOMICAL_MODEL (collections, objects, orphan data, report text)."""
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


def new_collection(name, parent):
    """New child collection linked under `parent`."""
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def make_material(name, rgba, roughness=0.55):
    """Principled material (+ viewport colour)."""
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
        from medverse.anatomy.classes import log                       # lazy import (avoids a circular import)
        log(f"[info] node material for {name} not created ({exc}); using viewport color only")
    mat.diffuse_color = rgba
    return mat


def srgb_to_linear(c):
    """sRGB (0..1) -> linear RGBA."""
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c[:3]) + (1.0,)


def build_mesh_object(name, verts_final, faces, flip_faces, collection, material, parent):
    """verts_final: (N,3) already in final world coords. Origin set to the median."""
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


def scale_about_own_center(verts, factor):
    """Scale vertices about their median."""
    if factor == 1.0:
        return verts
    c = np.median(verts, axis=0)
    return c + (verts - c) * factor


def bp3d_color(group, subgroup):
    """RGBA for a BodyParts3D (group, subgroup)."""
    return BP3D_COLORS.get((group, subgroup)) or BP3D_COLORS.get((group, None)) or (0.8, 0.8, 0.8, 1.0)


def model_objects(root_coll):
    """All objects in root_coll and its child collections."""
    out = []

    def walk(c):
        out.extend(c.objects)
        for ch in c.children:
            walk(ch)
    walk(root_coll)
    return out

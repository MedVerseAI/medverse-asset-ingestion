"""
01_export_bodyparts3d.py         (plain Python:  python scripts/pipeline/01_export_bodyparts3d.py)
------------------------
BodyParts3D  ->  clean, optimized, Blender-ready PLY pieces + manifest.

Inputs : data/raw/bodyparts3d/metadata/*.txt   and   data/interim/bodyparts3d/obj_*/**.obj
Needs  : the medverse package (pip install -e ".[export]"  or just run from the repo)

Division of labour:
    Human Brainnetome -> cerebral cortex
    BodyParts3D       -> everything else (this script)

Writes  data/interim/bodyparts3d/export_pieces/{meshes/<GROUP>/*.ply, manifest.json, reference/*.npz}
        data/processed/reports/export_bodyparts3d_report.txt
All settings live in medverse/anatomy/config.py, all paths in medverse/paths.py.
"""
import os
import sys
import re
import json
import importlib
import collections
import numpy as np

# ---------------------------------------------------------------------------
# Make `import medverse` work without `pip install -e .`
# (also works inside Blender; if __file__ is undefined, set MEDVERSE_ROOT)
# ---------------------------------------------------------------------------
import sys as _sys
import os as _os
from pathlib import Path as _Path


def _bootstrap():
    cands = []
    if _os.environ.get("MEDVERSE_ROOT"):
        cands.append(_Path(_os.environ["MEDVERSE_ROOT"]) / "src")
    try:
        cands.append(_Path(__file__).resolve().parents[2] / "src")
    except NameError:
        pass
    for c in cands:
        if (c / "medverse").is_dir():
            if str(c) not in _sys.path:
                _sys.path.insert(0, str(c))
            return


_bootstrap()


# ---------------------------------------------------------------------------
# Import project modules
# ---------------------------------------------------------------------------
from medverse.anatomy import config as anat_config
from medverse.anatomy import helpers as anat_helpers
from medverse.anatomy import classes as anat_classes

from medverse.anatomy.config import *  # noqa: E402,F401,F403
from medverse.anatomy.helpers import *  # noqa: E402,F401,F403
from medverse.anatomy.helpers import fast_simplification  # noqa: E402
from medverse.anatomy.classes import (
    log,
    Metadata,
    MeshIndex,
    reset_state,
)  # noqa: E402


# ============================================================================
# MAIN PIPELINE
# ============================================================================
def main():
    """Run the complete BodyParts3D export pipeline. Returns a process exit code."""
    reset_state()
    log.section("BodyParts3D export pipeline")
    log(f"BODYPARTS3D_BASE_PATH : {BODYPARTS3D_BASE_PATH}")
    log(f"OUTPUT_DIR            : {OUTPUT_DIR}")
    if not os.path.isdir(BODYPARTS3D_BASE_PATH):
        log("[error] BODYPARTS3D_BASE_PATH does not exist")
        return 2
    ensure_output_dirs()

    # ------------------------------------------------------------------ metadata
    files = find_metadata_files(BODYPARTS3D_BASE_PATH, METADATA_DIR)
    for k, p in files.items():
        log(f"metadata {k:15s}: {p}")
    meta = Metadata(files)
    log(f"concepts: {len(meta.name)} | element files (FJ): {len(meta.all_fjs)} | "
        f"isa concepts with elements: {len(meta.elements['isa'])} | partof: {len(meta.elements['partof'])}")

    # ------------------------------------------------------------------ muscles
    log.section("Muscle detection")
    muscle, n_tree = compute_muscle_elements(meta)
    log(f"elements tagged as muscle: {len(muscle)} (isa 'muscle organ' subtree: {n_tree}, "
        f"additional by name rules: {len(muscle) - n_tree})")
    muscle_by_region = collections.Counter()
    for fj in muscle:
        for n in meta.names_of(fj):
            if n.startswith("muscle of "):
                muscle_by_region[n] += 1
    for n, c in sorted(muscle_by_region.items()):
        log(f"   {n:40s} {c}")

    # ------------------------------------------------------------------ classification
    log.section("Structure discovery / classification")
    cls = classify_all(meta, muscle)
    inc = [r for r in cls.values() if r["decision"] == "include"]
    amb = [r for r in cls.values() if r["decision"] == "ambiguous"]
    exc_cortex = [r for r in cls.values() if r["group"] == "CORTEX_DUPLICATE"]
    exc_muscle = [r for r in cls.values() if r["reason"] == "muscle"]
    exc_other = [r for r in cls.values() if r["decision"] == "exclude" and r["group"] != "CORTEX_DUPLICATE"
                 and r["reason"] != "muscle"]
    out_of_scope = len(meta.all_fjs) - len(cls)
    log(f"elements in requested scope   : {len(cls)}")
    log(f"elements out of scope (body)  : {out_of_scope}   [limbs, organs, vessels, ... never loaded]")
    log(f"selected                      : {len(inc)}")
    log(f"excluded - cerebral cortex    : {len(exc_cortex)}  (Brainnetome is the source)")
    log(f"excluded - muscle in scope    : {len(exc_muscle)}")
    log(f"excluded - other / disabled   : {len(exc_other)}")
    log(f"AMBIGUOUS (excluded, reported): {len(amb)}")
    for r in exc_muscle:
        log(f"   [muscle excluded] {r['fj']} {r['label']}")
    for r in exc_other:
        log(f"   [excluded] {r['fj']} {r['label']} -> {r['reason']}")
    for r in amb:
        log(f"   [AMBIGUOUS] {r['fj']} {r['label']} -> {r['reason']}")

    # ------------------------------------------------------------------ mesh files
    log.section("Mesh files")
    obj_root = OBJ_SEARCH_DIR or BODYPARTS3D_BASE_PATH      # extracted OBJs live in data/interim
    index = MeshIndex(obj_root)
    log(f"{index.count} .obj files under {obj_root}")
    dups = sum(1 for v in index.by_stem.values() if len(v) > 1)
    if dups:
        log(f"[info] {dups} file names exist in several folders; shortest path (or matching isa/partof hint) wins")
    need = inc + exc_cortex
    resolved = sum(1 for r in need if index.find(r["fj"]))
    mode = MESH_SOURCE
    if mode == "auto":
        mode = "element" if need and resolved >= 0.5 * len(need) else "concept"
    log(f"element files resolvable: {resolved}/{len(need)} -> mesh source mode: {mode}")

    units_inc, prob1 = build_units(meta, inc, mode)
    units_cx, prob2 = build_units(meta, exc_cortex, mode)
    for p in prob1 + prob2:
        log(f"[warn] {p}")

    missing_files = []

    def load_units(units):
        loaded = []
        for u in units:
            obj_files = [index.find(s, u["hint"]) for s in u["stems"]]
            if any(p is None for p in obj_files):
                missing_files.append(u)
                continue
            vs, fs, off = [], [], 0
            for p in obj_files:
                v, f = read_obj(p)
                vs.append(v)
                fs.append(f + off)
                off += len(v)
            u["paths"] = obj_files
            u["verts"] = np.concatenate(vs)
            u["faces"] = np.concatenate(fs)
            loaded.append(u)
        return loaded

    loaded = load_units(units_inc)
    loaded_cx = load_units(units_cx)
    for u in missing_files:
        log(f"[MISSING FILE] {u['stems']} ({', '.join(r['label'] for r in u['recs'])})")
    if not loaded:
        log("[error] no meshes could be loaded. Check BODYPARTS3D_BASE_PATH / OBJ_SEARCH_DIR / MESH_SOURCE.")
        log.save(EXPORT_BP3D_REPORT_PATH)
        return 3

    def annotate(u):
        names = set()
        for r in u["recs"]:
            names |= set(r["names"])
        u["names"] = sorted(names)
        u["side"] = side_from_names(names)
        u["group"] = u["recs"][0]["group"]
        u["subgroup"] = u["recs"][0]["subgroup"]
        u["points"] = u["verts"]
    for u in loaded:
        annotate(u)
        u["cortex"] = False
    for u in loaded_cx:
        annotate(u)
        u["cortex"] = True

    # ------------------------------------------------------------------ frame
    log.section("Units and anatomical frame (BodyParts3D raw -> mm, RAS)")
    frame = infer_frame(loaded + loaded_cx)
    for m in frame["messages"]:
        log(f"[warn] {m}")
    factor = frame["unit_factor_to_mm"]
    M = np.asarray(frame["matrix_raw_to_ras"])
    flip = frame["determinant"] < 0
    log(f"unit factor raw->mm : {factor}")
    if "vertebral_length_raw" in frame:
        log(f"vertebral column raw length {frame['vertebral_length_raw']:.3f} -> "
            f"{frame['vertebral_length_raw'] * factor:.1f} mm")
    log(f"frame applied       : {frame['applied']} (confidence: {frame['confidence']})")
    if frame["applied"]:
        log("rows (raw-space directions of Right, Anterior, Superior):")
        for r, nm in zip(M, "RAS"):
            log(f"   {nm}: [{r[0]:+.4f} {r[1]:+.4f} {r[2]:+.4f}]")
        log(f"raw axis angles (deg): {frame['raw_axis_angles_deg']}  det={frame['determinant']:+.3f}")

    def to_ras(v):
        return (v @ M.T) * factor

    # ------------------------------------------------------------------ geometry
    log.section("Geometry cleaning / optimization")
    weld_raw = WELD_TOLERANCE_MM / factor
    tot_before = tot_after = 0
    for u in loaded:
        v, f, st = clean_mesh(u["verts"], u["faces"], weld_raw)
        if flip:
            f = f[:, ::-1].copy()
        v = to_ras(v)
        budget = FACE_BUDGET.get(u["group"], DEFAULT_FACE_BUDGET)
        v, f, dec, why = decimate(v, f, budget)
        u.update(cv=v, cf=f, stats=st, decimated=dec, dec_note=why)
        tot_before += st["raw_faces"]
        tot_after += len(f)

    def sort_key(u):
        code = spine_code(u["recs"][0]["label"])
        return (GROUP_ORDER.index(u["group"]), code_order(code), u["recs"][0]["label"], u["key"])
    loaded.sort(key=sort_key)
    label_count = collections.Counter(u["recs"][0]["label"] for u in loaded)
    for i, u in enumerate(loaded, 1):
        lab = u["recs"][0]["label"] if len(u["recs"]) == 1 else u["recs"][0]["label"] + "_x%d" % len(u["recs"])
        code = spine_code(u["recs"][0]["label"])
        cen = u["cv"].mean(0)
        side = u["side"]
        if not side and label_count[u["recs"][0]["label"]] > 1 and abs(cen[0]) > 1.0:
            side = "R" if cen[0] > 0 else "L"
        u["display_side"] = side
        base = sanitize(lab)
        if code and u["group"] in ("VERTEBRAE", "INTERVERTEBRAL_DISCS") and not base.startswith(code):
            base = f"{code}_{base}" if u["group"] == "VERTEBRAE" else f"{base}"
        if side and not re.search(r"(^|_)(left|right)(_|$)", base.lower()):
            base = f"{base}_{side}"
        u["name"] = f"{base}__{u['key']}"
        u["index"] = i

    mesh_dir = os.path.join(OUTPUT_DIR, "meshes")
    for g in GROUP_ORDER:
        os.makedirs(os.path.join(mesh_dir, g), exist_ok=True)
    manifest_structs = []
    for u in loaded:
        v, f = u["cv"], u["cf"]
        rel = os.path.join("meshes", u["group"], f"{u['index']:03d}_{u['name']}.ply")
        write_ply_binary(os.path.join(OUTPUT_DIR, rel), v, f)
        bb = [v.min(0).tolist(), v.max(0).tolist()]
        ext = (v.max(0) - v.min(0))
        st = u["stats"]
        log(f"{u['index']:03d} {u['group']:24s} {u['name'][:44]:44s} faces {st['raw_faces']:>7d} -> {len(f):>7d} "
            f"| closed={st['closed']} islands-={st['islands_removed']} dup-={st['duplicate']} "
            f"deg-={st['degenerate']}{' flipped' if st['flipped'] else ''}"
            f"{' DECIMATED' if u['decimated'] else ''} ext[mm]=({ext[0]:.1f},{ext[1]:.1f},{ext[2]:.1f})"
            f"{'  ' + u['dec_note'] if u['dec_note'] else ''}")
        manifest_structs.append({
            "index": u["index"], "name": u["name"], "label": u["recs"][0]["label"], "group": u["group"],
            "subgroup": u["subgroup"], "side": u["display_side"], "file": rel.replace("\\", "/"),
            "elements": u["fjs"], "concepts": sorted({c for r in u["recs"] for c in r["concepts"]}),
            "vertices": int(len(v)), "faces": int(len(f)), "raw_faces": int(st["raw_faces"]),
            "closed": bool(st["closed"]), "decimated": bool(u["decimated"]),
            "bbox_mm": bb, "centroid_mm": v.mean(0).tolist(), "is_muscle": False,
            "notes": sorted({n for r in u["recs"] for n in r["notes"]}),
        })
    log(f"\nfaces total (raw -> optimized): {tot_before} -> {tot_after}")
    if fast_simplification is None:
        log("[info] fast_simplification not installed: no decimation applied (pip install fast-simplification)")

    # ------------------------------------------------------------------ reference cloud (NOT a mesh)
    ref_pts = []
    for u in sorted(loaded_cx, key=lambda x: x["key"]):
        v, _, _ = clean_mesh(u["verts"], u["faces"], weld_raw)
        ref_pts.append(to_ras(v))
    ref_info = {"file": None, "points": 0, "elements": len(loaded_cx)}
    if ref_pts:
        allp = np.concatenate(ref_pts)
        sel = np.linspace(0, len(allp) - 1, min(REFERENCE_POINT_COUNT, len(allp))).astype(np.int64)
        os.makedirs(os.path.join(OUTPUT_DIR, "reference"), exist_ok=True)
        rp = os.path.join("reference", "cortex_reference_points.npz")
        np.savez_compressed(os.path.join(OUTPUT_DIR, rp), points=allp[sel].astype(np.float32))
        ref_info = {"file": rp.replace("\\", "/"), "points": int(len(sel)), "elements": len(loaded_cx),
                    "bbox_mm": [allp.min(0).tolist(), allp.max(0).tolist()]}
        log(f"\ncortex reference (registration only, not a model mesh): {len(loaded_cx)} elements, "
            f"{len(sel)} points, bbox {np.round(allp.min(0), 1).tolist()} .. {np.round(allp.max(0), 1).tolist()}")
    else:
        log("\n[warn] no cortex reference geometry could be loaded; the Blender script will fall back "
            "to landmarks / bounding boxes")

    # ------------------------------------------------------------------ landmarks + consistency checks
    landmarks = {}
    for u in loaded:
        for key, rx in LANDMARK_RX.items():
            if any(rx.search(n) for n in u["recs"][0]["own_names"]):
                s = u["display_side"] or "M"
                landmarks[f"{key}_{s}"] = u["cv"].mean(0).tolist()
    log(f"landmarks for registration: {sorted(landmarks)}")

    log.section("Anatomical sanity checks")
    by_group = collections.defaultdict(list)
    for u in loaded:
        by_group[u["group"]].append(u)
    cord = by_group.get("SPINAL_CORD", [])
    if cord:
        e = cord[0]["cv"].max(0) - cord[0]["cv"].min(0)
        log(f"spinal cord element extents [mm]: ({e[0]:.1f}, {e[1]:.1f}, {e[2]:.1f})")
        if min(e) < SPINAL_CORD_MIN_WIDTH_MM and sorted(e)[1] < SPINAL_CORD_MIN_WIDTH_MM:
            log(f"[WARN] the spinal-cord element is thinner than {SPINAL_CORD_MIN_WIDTH_MM} mm in two axes: "
                "it looks like a central-canal tube rather than a solid cord "
                "(the metadata registers the same file under both names).")
        bs = by_group.get("BRAINSTEM", [])
        if bs:
            zb = min(u["cv"][:, 2].min() for u in bs)
            zc = cord[0]["cv"][:, 2].max()
            log(f"brainstem lowest z = {zb:.1f} mm | spinal cord highest z = {zc:.1f} mm | "
                f"gap = {zb - zc:+.1f} mm  ({'overlap' if zb - zc < 0 else 'gap'})")
    verts_g = sorted(by_group.get("VERTEBRAE", []), key=lambda u: u["cv"][:, 2].mean(), reverse=True)
    discs = by_group.get("INTERVERTEBRAL_DISCS", [])
    if cord and verts_g:
        zc0, zc1 = cord[0]["cv"][:, 2].min(), cord[0]["cv"][:, 2].max()
        log(f"spinal cord z-range {zc0:.1f}..{zc1:.1f} mm vs vertebral column z-range "
            f"{min(u['cv'][:, 2].min() for u in verts_g):.1f}..{max(u['cv'][:, 2].max() for u in verts_g):.1f} mm")
    for d in discs:
        if not spine_code(d["recs"][0]["label"]):
            zc = d["cv"][:, 2].mean()
            above = [u for u in verts_g if u["cv"][:, 2].mean() > zc]
            below = [u for u in verts_g if u["cv"][:, 2].mean() <= zc]
            ua = spine_code(above[-1]["recs"][0]["label"]) if above else "?"
            ub = spine_code(below[0]["recs"][0]["label"]) if below else "?"
            note = (f"disc '{d['recs'][0]['label']}' ({d['key']}) has no level in the metadata; by geometry it lies "
                    f"between {ua} and {ub} (derived, not metadata)")
            log(f"[info] {note}")
            for ms in manifest_structs:
                if ms["index"] == d["index"]:
                    ms["notes"].append(note)

    # ------------------------------------------------------------------ requested-anatomy checklist
    log.section("Requested anatomy: found / missing")
    cnt = collections.Counter((u["group"], u["subgroup"]) for u in loaded)
    missing = []

    def check(label, got, expected=None):
        ok = got >= (expected if expected else 1)
        log(f"   [{'ok' if ok else 'MISSING'}] {label}: {got}" + (f" / {expected}" if expected else ""))
        if not ok:
            missing.append(label)
    check("cervical vertebrae (atlas, axis, C3-C7)", cnt[("VERTEBRAE", "cervical")], 7)
    check("thoracic vertebrae", cnt[("VERTEBRAE", "thoracic")], 12)
    check("lumbar vertebrae", cnt[("VERTEBRAE", "lumbar")], 5)
    check("sacrum", cnt[("VERTEBRAE", "sacral")], 1)
    n_coccyx = len([c for c, n in meta.name.items() if COCCYX_RX.search(n.lower())
                    and meta.elements["partof"].get(c)])
    check("coccyx (present in metadata)", n_coccyx, 1)
    check("intervertebral discs (C2-C3 ... L5-S1 = 23 expected)", len(discs), 23)
    check("spinal cord", len(cord), 1)
    n_sn = len([c for c, n in meta.name.items() if SPINAL_NERVE_SEARCH_RX.search(n.lower())])
    check("spinal nerves / roots / cauda equina (concepts in metadata)", n_sn, 1)
    log("   [info] spinal-associated cartilage: only the intervertebral discs (articular disk of symphysis) "
        "exist in the metadata; costal/nasal/laryngeal cartilage belongs to unrelated anatomy and is not exported")
    check("cerebellum", cnt[("CEREBELLUM", "cerebellum")])
    check("midbrain", cnt[("BRAINSTEM", "midbrain")])
    check("pons", cnt[("BRAINSTEM", "pons")])
    check("medulla oblongata", cnt[("BRAINSTEM", "medulla_oblongata")])
    for key in LANDMARK_RX:
        check(f"{key} (deep structure)", sum(1 for k in landmarks if k.startswith(key + "_")), 2)
    check("hypothalamus / diencephalon pieces", cnt[("SUBCORTICAL_STRUCTURES", "deep_gray_matter")])
    if cnt[("OTHER_BRAIN_STRUCTURES", "ventricular_system")] == 0 and INCLUDE_VENTRICULAR_SYSTEM:
        missing.append("ventricular system")
    for r in amb:
        log(f"   [ambiguous - not exported] {r['fj']} {r['label']}: {r['reason']}")
    for u in missing_files:
        missing.append("mesh file for " + ", ".join(r["label"] for r in u["recs"]))

    # ------------------------------------------------------------------ manifest
    manifest = {
        "schema": 1,
        "dataset": {"base_path": BODYPARTS3D_BASE_PATH, "metadata_files": files, "mesh_source": mode,
                    "obj_files_found": index.count, "elements_in_dataset": len(meta.all_fjs)},
        "frame": {"unit_factor_raw_to_mm": factor, "applied": frame["applied"],
                  "confidence": frame["confidence"], "matrix_raw_to_ras": frame["matrix_raw_to_ras"],
                  "determinant": frame["determinant"], "messages": frame["messages"],
                  "output_space": "RAS, millimetres (x=Right, y=Anterior, z=Superior)"},
        "structures": manifest_structs,
        "reference": ref_info,
        "landmarks_mm": landmarks,
        "excluded": {
            "muscle_elements_in_dataset": len(muscle),
            "muscle_elements_in_scope": [r["fj"] for r in exc_muscle],
            "cortex_duplicates": [{"element": r["fj"], "label": r["label"]} for r in exc_cortex],
            "other": [{"element": r["fj"], "label": r["label"], "reason": r["reason"]} for r in exc_other],
        },
        "ambiguous": [{"element": r["fj"], "label": r["label"], "reason": r["reason"]} for r in amb],
        "missing": missing,
        "options": {"ventricles": INCLUDE_VENTRICULAR_SYSTEM, "white_matter": INCLUDE_CEREBRAL_WHITE_MATTER,
                    "cranial_nerves": INCLUDE_CRANIAL_NERVES},
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)

    log.section("Summary")
    log(f"exported pieces        : {len(loaded)}")
    for g in GROUP_ORDER:
        n = sum(1 for u in loaded if u["group"] == g)
        if n:
            log(f"   {g:26s}{n}")
    log(f"muscle structures      : excluded ({len(muscle)} muscle elements in dataset, "
        f"{len(exc_muscle)} inside requested scope); exported muscle pieces: 0")
    log(f"missing / not available: {missing if missing else 'none'}")
    log(f"ambiguous (excluded)   : {len(amb)}")
    log(f"output location        : {OUTPUT_DIR}")
    log.save(EXPORT_BP3D_REPORT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())

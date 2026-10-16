"""Blender entry point for Brainnetome + BodyParts3D integration.

Run this file from Blender 4.0+ after the two dataset exports are ready.
The pipeline algorithms and scene-building function bodies are preserved.
"""
import os
import sys
import re
import json
import math
import collections
import numpy as np
import bpy

# ----------------------------------------------------------------------------
# Make the sibling modules (anat_config.py, ...) importable.
# Blender's Text Editor often gives a useless __file__, so we try several places and pick the first
# folder that really contains anat_config.py.
# If everything fails, set MANUAL_SCRIPT_DIR below to your scripts folder.
# ----------------------------------------------------------------------------
MANUAL_SCRIPT_DIR = r"E:\Programs\blender\data\final_3D\V0.4\brainnetome_bodyparts3d_project\scripts"


def _find_script_dir():
    cands = []
    root = os.environ.get("ANAT_PROJECT_ROOT")
    if root:
        cands.append(os.path.join(root, "scripts"))
    try:
        cands.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    try:                                                   # script opened from a file in the Text Editor
        t = bpy.context.space_data.text
        if t is not None and t.filepath:
            cands.append(os.path.dirname(bpy.path.abspath(t.filepath)))
    except Exception:
        pass
    if bpy.data.filepath:                                  # relative to the saved .blend
        d = os.path.dirname(bpy.data.filepath)
        cands += [d, os.path.join(d, "scripts"), os.path.join(os.path.dirname(d), "scripts")]
    cands.append(MANUAL_SCRIPT_DIR)
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "anat_config.py")):
            return c
    raise ModuleNotFoundError(
        "anat_config.py not found. Tried:\n  " + "\n  ".join(str(c) for c in cands) +
        "\nSet MANUAL_SCRIPT_DIR at the top of this file to your scripts folder.")


_SCRIPT_DIR = _find_script_dir()
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Blender keeps imported modules alive between runs: reload them so edits to the config files are picked up.
import importlib
import anat_config, anat_helpers, anat_classes                         # noqa: E402
import integration_config, integration_geometry, integration_data      # noqa: E402
for _m in (anat_config, anat_helpers, anat_classes,
           integration_config, integration_geometry, integration_data):
    importlib.reload(_m)

from integration_config import *
from integration_geometry import *
from integration_data import *

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

Loads both anatomical sources, registers them, builds the Blender scene, audits the result,
writes the final report and saves everything under outputs/ (reports/ and final/)."""
    reset_state()
    ensure_output_dirs()
    missing_inputs = check_inputs()
    if missing_inputs:
        raise FileNotFoundError(f"missing input path(s): {missing_inputs}")
    log.section("Brainnetome + BodyParts3D integration")
    bn = load_brainnetome()
    bp = load_bodyparts3d()
    place = compute_placement(bn, bp)
    root_obj, root_coll, _ = build_scene(bn, bp, place)
    audit_scene(root_coll)
    geometry_report(bn, bp, place)
    final_report(root_obj, root_coll, place, bn, bp)
    setup_viewport()

    # ---- save outputs (everything generated goes under outputs/) ----
    report_path = os.path.join(REPORTS_DIR, "integration_report.txt")
    blend_path = os.path.join(FINAL_DIR, "anatomical_model.blend")
    log("\nDone. Full report: Text Editor -> ANATOMICAL_MODEL_REPORT (also stored on the root empty).")
    log(f"report saved : {report_path}")
    log(f"blend saved  : {blend_path}")
    log.save(report_path)
    # copy=True: write the .blend without switching the currently open Blender file to the new path
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, copy=True)


if __name__ == "__main__":
    main()
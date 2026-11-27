"""Blender scene builder.  Runs INSIDE Blender (imports bpy lazily).  Input: a SceneSpec (organization.py)."""
from __future__ import annotations

import math
import os

import numpy as np


def _bpy():
    import bpy
    return bpy


def srgb_to_linear(c):
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c[:3]) + (1.0,)


def clear_previous_model(spec):
    bpy = _bpy()
    root = bpy.data.collections.get(spec["root_name"])
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
    for ob in [o for o in bpy.data.objects if o.name == spec["root_name"]]:
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in [m for m in bpy.data.materials if m.name.startswith(spec["material_prefix"]) and m.users == 0]:
        bpy.data.materials.remove(m)


def make_material(name, rgba, roughness=0.55):
    bpy = _bpy()
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
    except Exception:
        pass                                              # never fail the build because of shading
    mat.diffuse_color = rgba
    return mat


def build_scene(spec: dict, spec_dir: str) -> dict:
    """Create the integrated, organized scene.  -> audit dict (counts per collection + materials)."""
    from medverse.geometry.meshio import read_ply_binary
    bpy = _bpy()
    clear_previous_model(spec)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "MILLIMETERS"
    root_coll = bpy.data.collections.new(spec["root_name"])
    scene.collection.children.link(root_coll)
    colls = {(): root_coll}
    for path in spec["collections"]:
        key = tuple(path)
        c = bpy.data.collections.new(path[-1])
        colls[key[:-1]].children.link(c)
        colls[key] = c
    helpers = bpy.data.collections.new("HELPERS_METADATA")
    root_coll.children.link(helpers)
    root_obj = bpy.data.objects.new(spec["root_name"], None)
    root_obj.empty_display_type = "PLAIN_AXES"
    root_obj.empty_display_size = 0.05
    helpers.objects.link(root_obj)
    u = spec["units_per_mm"]
    materials, per_coll = {}, {}
    for o in spec["objects"]:
        v, f, _ = read_ply_binary(os.path.join(spec_dir, o["file"]))
        v = v * u
        c = np.median(v, axis=0)
        mesh = bpy.data.meshes.new(o["name"])
        mesh.from_pydata((v - c).astype(np.float32).tolist(), [], f.astype(np.int64).tolist())
        mesh.update()
        mesh.validate()
        try:
            mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=bool))
        except Exception:
            pass
        obj = bpy.data.objects.new(o["name"], mesh)
        coll = colls[tuple(o["collection"])]
        coll.objects.link(obj)
        obj.location = tuple(c.tolist())
        obj.parent = root_obj
        mk = o["material"]
        if mk not in materials:
            materials[mk] = make_material(spec["material_prefix"] + mk.replace(":", "_"), srgb_to_linear(o["rgba"]))
        mesh.materials.append(materials[mk])
        for k, val in o["props"].items():
            obj[k] = val
        per_coll["/".join(o["collection"])] = per_coll.get("/".join(o["collection"]), 0) + 1
    for h in spec["helpers"]:
        e = bpy.data.objects.new(h["name"], None)
        e.empty_display_type, e.empty_display_size = "SPHERE", 3.0 * u
        e.location = tuple((np.asarray(h["location_mm"]) * u).tolist())
        helpers.objects.link(e)
        e.hide_viewport = True
    return {
        "objects": len(spec["objects"]),
        "materials": len(materials),
        "per_collection": per_coll,
        "helpers": len(spec["helpers"]),
    }


def purge_scene_except_model(spec):
    bpy = _bpy()
    root = bpy.data.collections.get(spec["root_name"])
    keep = set()

    def walk(c):
        keep.update(o.name for o in c.objects)
        for ch in c.children:
            walk(ch)
    if root is not None:
        walk(root)
    for o in list(bpy.data.objects):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)


def _model_bbox(root_name: str):
    """Compute world-space (lo, hi) across all MESH objects in ``root_name``."""
    objs = list_model_objects(root_name)
    if not objs:
        return np.zeros(3), np.ones(3)
    pts = []
    for o in objs:
        M = np.asarray(o.matrix_world, dtype=float)
        corners = np.asarray([list(c) for c in o.bound_box], dtype=float)
        pts.append(corners @ M[:3, :3].T + M[:3, 3])
    all_pts = np.concatenate(pts, axis=0)
    return all_pts.min(axis=0), all_pts.max(axis=0)


def setup_viewport(spec):
    """Configure every 3D viewport across bpy.data.screens (works in --background mode too)."""
    try:
        bpy = _bpy()
        import mathutils

        vp = spec.get("viewport", {})
        shading = vp.get("shading", "SOLID")
        euler_deg = vp.get("euler_deg", [80.0, 0.0, 155.0])
        distance_factor = float(vp.get("distance_factor", 3.2))
        hide_grid = bool(vp.get("hide_grid", True))

        center, size = np.zeros(3), 1.0
        try:
            bpy.context.view_layer.update()
            lo, hi = _model_bbox(spec["root_name"])
            center = (lo + hi) / 2.0
            size = float(np.max(hi - lo)) or 1.0
        except Exception:
            pass

        rot = mathutils.Euler(tuple(math.radians(a) for a in euler_deg), "XYZ").to_quaternion()
        for screen in bpy.data.screens:  # bpy.context.screen is None in --background mode
            for area in screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for sp in area.spaces:
                    if sp.type != "VIEW_3D":
                        continue
                    sp.shading.type = shading
                    if shading == "SOLID":
                        sp.shading.color_type = "MATERIAL"
                    sp.clip_start = 0.001
                    sp.clip_end = 100.0
                    if hide_grid:
                        sp.overlay.show_floor = False
                        sp.overlay.show_axis_x = False
                        sp.overlay.show_axis_y = False
                        sp.overlay.show_axis_z = False
                    r3d = sp.region_3d
                    if r3d is not None:
                        r3d.view_perspective = "PERSP"
                        r3d.view_location = tuple(center.tolist())
                        r3d.view_rotation = rot
                        r3d.view_distance = max(size * distance_factor, 0.05)

        try:
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            bpy.context.view_layer.objects.active = None
        except Exception:
            pass
    except Exception:
        pass


def list_model_objects(root_name: str) -> list:
    bpy = _bpy()
    root = bpy.data.collections.get(root_name)
    out = []

    def walk(c):
        out.extend(o for o in c.objects if o.type == "MESH")
        for ch in c.children:
            walk(ch)
    if root is not None:
        walk(root)
    return out

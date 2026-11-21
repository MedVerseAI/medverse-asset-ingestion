"""Blender scene builder.  Runs INSIDE Blender (imports bpy lazily).  Input: a SceneSpec (organization.py)."""
from __future__ import annotations

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
    """Create the integrated, organized scene.  -> audit dict (counts per collection)."""
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
    return {"objects": len(spec["objects"]), "per_collection": per_coll, "helpers": len(spec["helpers"])}


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


def setup_viewport(spec):
    """Best-effort viewport setup (SOLID shading, no grid, 3/4 view).  Never fails the export."""
    try:
        bpy = _bpy()
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    sp = area.spaces[0]
                    sp.shading.type = spec["viewport"]["shading"]
                    if spec["viewport"]["hide_grid"]:
                        sp.overlay.show_floor = False
                        sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
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

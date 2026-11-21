"""Executed INSIDE Blender:  blender -b --factory-startup --python blender_entry.py -- <cmd> <args.json>

cmd = build | finalize | fbx.   Writes <args.result_path> (JSON) in every case, including failures.
"""
import json
import os
import sys
import traceback


def _args():
    i = sys.argv.index("--")
    cmd, path = sys.argv[i + 1], sys.argv[i + 2]
    with open(path, encoding="utf-8") as fh:
        return cmd, json.load(fh)


def _count_meshes():
    import bpy
    return sum(1 for o in bpy.data.objects if o.type == "MESH")


def main():
    cmd, a = _args()
    sys.path.insert(0, a["src_dir"])
    result = {"cmd": cmd, "status": "failed"}
    try:
        import bpy
        from medverse.scene import builder
        with open(a["spec_path"], encoding="utf-8") as fh:
            spec = json.load(fh)
        spec_dir = os.path.dirname(os.path.dirname(os.path.abspath(a["spec_path"])))
        if cmd == "build":
            audit = builder.build_scene(spec, spec_dir)
            os.makedirs(os.path.dirname(a["work_blend"]), exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=a["work_blend"], compress=True)
            result.update(status="ok", audit=audit, meshes=_count_meshes(), blend=a["work_blend"])
        elif cmd == "finalize":
            bpy.ops.wm.open_mainfile(filepath=a["work_blend"])
            if spec["clean_scene"]:
                builder.purge_scene_except_model(spec)
            builder.setup_viewport(spec)
            os.makedirs(os.path.dirname(a["out_blend"]), exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=a["out_blend"], compress=True)
            bpy.ops.wm.open_mainfile(filepath=a["out_blend"])                 # verification: it really opens
            n = len(builder.list_model_objects(spec["root_name"]))
            result.update(status="ok" if n == len(spec["objects"]) else "failed", reopened_meshes=n,
                          expected_meshes=len(spec["objects"]), file=a["out_blend"],
                          size_bytes=os.path.getsize(a["out_blend"]))
        elif cmd == "fbx":
            if a.get("source", "auto") == "auto" and os.path.isfile(a.get("work_blend", "")):
                bpy.ops.wm.open_mainfile(filepath=a["work_blend"])
                result["scene_source"] = "work_blend"
            else:
                builder.build_scene(spec, spec_dir)
                result["scene_source"] = "spec"
            for o in [o for o in bpy.data.objects if o.name.startswith("LM_")]:        # landmarks are not for Unity
                bpy.data.objects.remove(o, do_unlink=True)
            os.makedirs(os.path.dirname(a["out_fbx"]), exist_ok=True)
            bpy.ops.export_scene.fbx(filepath=a["out_fbx"], use_selection=False, object_types={"MESH", "EMPTY"},
                                     apply_unit_scale=a["apply_unit_scale"], axis_forward=a["axis_forward"],
                                     axis_up=a["axis_up"], bake_space_transform=a["bake_space_transform"],
                                     add_leaf_bones=False, mesh_smooth_type="FACE")
            exported = _count_meshes()
            result.update(file=a["out_fbx"], size_bytes=os.path.getsize(a["out_fbx"]), exported_meshes=exported)
            if a.get("verify_reimport", True):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                bpy.ops.import_scene.fbx(filepath=a["out_fbx"])
                n = _count_meshes()
                result.update(reimported_meshes=n)
                result["status"] = "ok" if n == len(spec["objects"]) else "failed"
            else:
                result["status"] = "ok"
        else:
            raise ValueError(f"unknown command {cmd}")
    except BaseException as exc:                                                         # noqa: BLE001
        result.update(status="failed", error=str(exc), traceback=traceback.format_exc())
    with open(a["result_path"], "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    if result["status"] != "ok":
        sys.exit(1)


main()

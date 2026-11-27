"""Executed INSIDE Blender:  blender -b --factory-startup --python blender_entry.py -- <cmd> <args.json>

cmd = build | finalize | fbx | glb.   Writes <args.result_path> (JSON) in every case, including failures.
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


def _scene_stats():
    import bpy
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    total_verts = 0
    total_tris = 0
    mat_names = set()
    for o in meshes:
        mesh = o.data
        total_verts += len(mesh.vertices)
        mesh.calc_loop_triangles()
        total_tris += len(mesh.loop_triangles)
        for mat in mesh.materials:
            if mat is not None:
                mat_names.add(mat.name)
    leaked_lm = [o.name for o in bpy.data.objects if o.name.startswith("LM_")]
    return {
        "meshes": len(meshes),
        "vertices": total_verts,
        "triangles": total_tris,
        "materials": len(mat_names),
        "leaked_landmarks": len(leaked_lm),
    }


def _strip_landmarks_and_defaults(spec):
    import bpy
    from medverse.scene import builder
    if spec.get("clean_scene", True):
        builder.purge_scene_except_model(spec)
    for o in [o for o in bpy.data.objects if o.name.startswith("LM_")]:
        bpy.data.objects.remove(o, do_unlink=True)


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
            if spec.get("clean_scene", True):
                builder.purge_scene_except_model(spec)
            os.makedirs(os.path.dirname(a["work_blend"]), exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=a["work_blend"], compress=True)
            st = _scene_stats()
            result.update(
                status="ok",
                audit=audit,
                meshes=st["meshes"],
                triangles=st["triangles"],
                materials=st["materials"],
                blend=a["work_blend"],
            )

        elif cmd == "finalize":
            bpy.ops.wm.open_mainfile(filepath=a["work_blend"])
            if spec["clean_scene"]:
                builder.purge_scene_except_model(spec)
            builder.setup_viewport(spec)
            os.makedirs(os.path.dirname(a["out_blend"]), exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=a["out_blend"], compress=True)
            bpy.ops.wm.open_mainfile(filepath=a["out_blend"])                 # verification: it really opens
            n = len(builder.list_model_objects(spec["root_name"]))
            st = _scene_stats()
            result.update(
                status="ok" if n == len(spec["objects"]) else "failed",
                reopened_meshes=n,
                expected_meshes=len(spec["objects"]),
                triangles=st["triangles"],
                materials=st["materials"],
                file=a["out_blend"],
                size_bytes=os.path.getsize(a["out_blend"]),
            )

        elif cmd == "fbx":
            if a.get("source", "auto") == "auto" and os.path.isfile(a.get("work_blend", "")):
                bpy.ops.wm.open_mainfile(filepath=a["work_blend"])
                result["scene_source"] = "work_blend"
            else:
                builder.build_scene(spec, spec_dir)
                result["scene_source"] = "spec"
            _strip_landmarks_and_defaults(spec)
            os.makedirs(os.path.dirname(a["out_fbx"]), exist_ok=True)
            bpy.ops.export_scene.fbx(
                filepath=a["out_fbx"],
                use_selection=False,
                object_types={"MESH", "EMPTY"},
                apply_unit_scale=a["apply_unit_scale"],
                axis_forward=a["axis_forward"],
                axis_up=a["axis_up"],
                bake_space_transform=a["bake_space_transform"],
                add_leaf_bones=False,
                mesh_smooth_type="FACE",
            )
            exported = _scene_stats()
            result.update(
                file=a["out_fbx"],
                size_bytes=os.path.getsize(a["out_fbx"]),
                exported_meshes=exported["meshes"],
                triangles=exported["triangles"],
                materials=exported["materials"],
                leaked_landmarks=exported["leaked_landmarks"],
            )
            if a.get("verify_reimport", True):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                bpy.ops.import_scene.fbx(filepath=a["out_fbx"])
                reimp = _scene_stats()
                result.update(
                    reimported_meshes=reimp["meshes"],
                    reimported_triangles=reimp["triangles"],
                    reimported_materials=reimp["materials"],
                    reimported_leaked_landmarks=reimp["leaked_landmarks"],
                )
                ok = reimp["meshes"] == len(spec["objects"]) and reimp["leaked_landmarks"] == 0
                result["status"] = "ok" if ok else "failed"
            else:
                result["status"] = "ok"

        elif cmd == "glb":
            if a.get("source", "auto") == "auto" and os.path.isfile(a.get("work_blend", "")):
                bpy.ops.wm.open_mainfile(filepath=a["work_blend"])
                result["scene_source"] = "work_blend"
            else:
                builder.build_scene(spec, spec_dir)
                result["scene_source"] = "spec"
            _strip_landmarks_and_defaults(spec)
            os.makedirs(os.path.dirname(a["out_glb"]), exist_ok=True)
            bpy.ops.export_scene.gltf(
                filepath=a["out_glb"],
                export_format="GLB",
                export_extras=bool(a.get("export_extras", True)),
                export_draco_mesh_compression_enable=bool(a.get("draco_compression", True)),
                export_draco_mesh_compression_level=int(a.get("draco_level", 6)),
                export_materials="EXPORT",
                export_apply=True,
            )
            exported = _scene_stats()
            result.update(
                file=a["out_glb"],
                size_bytes=os.path.getsize(a["out_glb"]),
                exported_meshes=exported["meshes"],
                triangles=exported["triangles"],
                materials=exported["materials"],
                leaked_landmarks=exported["leaked_landmarks"],
            )
            if a.get("verify_reimport", True):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                bpy.ops.import_scene.gltf(filepath=a["out_glb"])
                reimp = _scene_stats()
                result.update(
                    reimported_meshes=reimp["meshes"],
                    reimported_triangles=reimp["triangles"],
                    reimported_materials=reimp["materials"],
                    reimported_leaked_landmarks=reimp["leaked_landmarks"],
                )
                ok = reimp["meshes"] == len(spec["objects"]) and reimp["leaked_landmarks"] == 0
                result["status"] = "ok" if ok else "failed"
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

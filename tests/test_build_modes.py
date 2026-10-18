"""
End-to-end check of step 03 in each mode, using synthetic data and a fake `bpy`
(no Blender, no real datasets needed). Runs in a subprocess so every mode gets a clean interpreter.
"""
import json
import os
import pathlib
import subprocess
import sys
import textwrap

import numpy as np
import pytest

from medverse.anatomy.helpers import write_ply_binary

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = pathlib.Path(__file__).resolve().parent


def sphere(center, radii, n_lat=8, n_lon=12):
    verts = [(0, 0, 1)]
    for i in range(1, n_lat):
        th = np.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * np.pi * j / n_lon
            verts.append((np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)))
    verts.append((0, 0, -1))
    faces = []
    for j in range(n_lon):
        faces.append((0, 1 + j, 1 + (j + 1) % n_lon))
    for i in range(n_lat - 2):
        for j in range(n_lon):
            a, b = 1 + i * n_lon + j, 1 + i * n_lon + (j + 1) % n_lon
            faces += [(a, a + n_lon, b), (b, a + n_lon, b + n_lon)]
    last = len(verts) - 1
    for j in range(n_lon):
        faces.append((last, 1 + (n_lat - 2) * n_lon + (j + 1) % n_lon, 1 + (n_lat - 2) * n_lon + j))
    v = np.asarray(verts) * np.asarray(radii) + np.asarray(center)
    return v.astype(np.float32), np.asarray(faces, dtype=np.int32)


def make_dataset(data):
    bn = data / "interim" / "brainnetome" / "voxel_export_pieces"
    bn.mkdir(parents=True)
    for rid, name, cx in ((1, "SFG_L", -35.0), (2, "SFG_R", 35.0)):
        v, f = sphere((cx, -15, 10), (35, 70, 55))
        write_ply_binary(str(bn / f"{rid:03d}_{name}.ply"), v, f)

    ex = data / "interim" / "bodyparts3d" / "export_pieces"
    structs = [
        ("CEREBELLUM", "cerebellum", "", (0, -55, -35), (40, 30, 25)),
        ("BRAINSTEM", "pons", "pons", (0, -30, -45), (12, 12, 25)),
        ("SUBCORTICAL_STRUCTURES", "left thalamus", "L", (-10, -15, 5), (10, 15, 10)),
        ("VERTEBRAE", "C1_atlas", "", (0, -40, -80), (20, 20, 8)),
        ("SPINAL_CORD", "spinal cord", "", (0, -40, -200), (6, 6, 110)),
        ("CEREBRAL_CORTEX", "left precentral gyrus", "L", (-30, -10, 40), (15, 25, 15)),
        ("CEREBRAL_CORTEX", "right precentral gyrus", "R", (30, -10, 40), (15, 25, 15)),
    ]
    manifest_structs = []
    for i, (group, label, side, c, r) in enumerate(structs, 1):
        (ex / "meshes" / group).mkdir(parents=True, exist_ok=True)
        v, f = sphere(c, r)
        rel = f"meshes/{group}/{i:03d}_{label.replace(' ', '_')}.ply"
        write_ply_binary(str(ex / rel), v, f)
        manifest_structs.append({
            "index": i, "name": f"{label.replace(' ', '_')}__FJ{i:04d}", "label": label, "group": group,
            "subgroup": "x", "side": side if side in ("L", "R") else "", "file": rel, "elements": [f"FJ{i:04d}"],
            "concepts": ["FMA1"], "is_muscle": False})
    (ex / "reference").mkdir()
    ref, _ = sphere((0, -15, 10), (72, 90, 58), 30, 40)
    np.savez_compressed(ex / "reference" / "cortex_reference_points.npz", points=ref)
    manifest = {
        "schema": 1,
        "dataset": {"mesh_source": "element"},
        "frame": {"unit_factor_raw_to_mm": 1.0, "applied": True, "confidence": "ok",
                  "output_space": "RAS mm", "messages": []},
        "structures": manifest_structs,
        "reference": {"file": "reference/cortex_reference_points.npz", "elements": 2},
        "landmarks_mm": {}, "excluded": {}, "ambiguous": [], "missing": [],
        "options": {"export_bp3d_cortex": True},
    }
    (ex / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


DRIVER = textwrap.dedent("""
    import json, runpy, sys
    sys.path.insert(0, {tests!r})
    import fake_bpy
    state = fake_bpy.install()
    runpy.run_path({script!r}, run_name="__main__")
    bpy = state["bpy"]
    print("@@" + json.dumps({{
        "objects": [[o.name, o.get("source"), o.get("bp3d_group")] for o in bpy.data.objects if o.type == "MESH"],
        "collections": [c.name for c in bpy.data.collections],
        "saved": state["saved"],
    }}))
""")


def run_mode(tmp_path, mode):
    data = tmp_path / "data"
    make_dataset(data)
    env = dict(os.environ, MEDVERSE_DATA_DIR=str(data), PYTHONPATH=str(ROOT / "src"))
    env.pop("MEDVERSE_CONFIG", None)
    script = ROOT / "scripts" / "pipeline" / "03_integrate_brainnetome_bodyparts3d.py"
    code = DRIVER.format(tests=str(TESTS), script=str(script))
    proc = subprocess.run([sys.executable, "-c", code, "--", "--mode", mode], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("@@"))
    return json.loads(line[2:]), data


def sources(result):
    return {o[1] for o in result["objects"]}


def groups(result):
    return {o[2] for o in result["objects"] if o[1] == "BodyParts3D"}


def test_mode_brainnetome_only_cortex(tmp_path):
    res, data = run_mode(tmp_path, "brainnetome")
    assert sources(res) == {"Human Brainnetome"}
    assert len(res["objects"]) == 2
    assert "SPINAL_SYSTEM" not in res["collections"]
    assert "CEREBRAL_CORTEX_BRAINNETOME" in res["collections"]
    assert pathlib.Path(res["saved"]).name == "anatomical_model_brainnetome.blend"
    assert (data / "processed" / "reports" / "integration_report_brainnetome.txt").is_file()


def test_mode_bodyparts3d_has_own_cortex_and_spine(tmp_path):
    res, data = run_mode(tmp_path, "bodyparts3d")
    assert sources(res) == {"BodyParts3D"}
    assert groups(res) == {"CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES", "VERTEBRAE", "SPINAL_CORD",
                           "CEREBRAL_CORTEX"}
    assert "CEREBRAL_CORTEX_BODYPARTS3D" in res["collections"]
    assert "CEREBRAL_CORTEX_BRAINNETOME" not in res["collections"]
    assert pathlib.Path(res["saved"]).name == "anatomical_model_bodyparts3d.blend"


def test_mode_integrated_uses_brainnetome_cortex_not_bodyparts3d_cortex(tmp_path):
    res, data = run_mode(tmp_path, "integrated")
    assert sources(res) == {"Human Brainnetome", "BodyParts3D"}
    assert "CEREBRAL_CORTEX" not in groups(res)            # stale BP3D cortex in the manifest is ignored
    assert {"VERTEBRAE", "SPINAL_CORD", "CEREBELLUM"} <= groups(res)
    assert "SPINAL_SYSTEM" in res["collections"] and "CEREBRAL_CORTEX_BRAINNETOME" in res["collections"]
    assert pathlib.Path(res["saved"]).name == "anatomical_model.blend"      # historical name kept


def test_disabled_groups_are_dropped(tmp_path):
    cfg = tmp_path / "brain_only.toml"
    cfg.write_text('[model]\nmode = "bodyparts3d"\n[bodyparts3d]\n'
                   'enabled_groups = ["CEREBELLUM", "BRAINSTEM", "CEREBRAL_CORTEX"]\n', encoding="utf-8")
    data = tmp_path / "data"
    make_dataset(data)
    env = dict(os.environ, MEDVERSE_DATA_DIR=str(data), PYTHONPATH=str(ROOT / "src"))
    script = ROOT / "scripts" / "pipeline" / "03_integrate_brainnetome_bodyparts3d.py"
    code = DRIVER.format(tests=str(TESTS), script=str(script))
    proc = subprocess.run([sys.executable, "-c", code, "--", "--config", str(cfg)], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    res = json.loads(next(l for l in proc.stdout.splitlines() if l.startswith("@@"))[2:])
    assert groups(res) == {"CEREBELLUM", "BRAINSTEM", "CEREBRAL_CORTEX"}
    assert "SPINAL_SYSTEM" not in res["collections"]


def test_missing_inputs_give_actionable_error(tmp_path):
    env = dict(os.environ, MEDVERSE_DATA_DIR=str(tmp_path / "empty"), PYTHONPATH=str(ROOT / "src"))
    script = ROOT / "scripts" / "pipeline" / "03_integrate_brainnetome_bodyparts3d.py"
    code = DRIVER.format(tests=str(TESTS), script=str(script))
    proc = subprocess.run([sys.executable, "-c", code, "--", "--mode", "brainnetome"], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "run_pipeline.py --mode brainnetome" in proc.stderr

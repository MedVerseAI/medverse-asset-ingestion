"""Scene organization (pure python, no bpy): turns final assets + decisions into a SceneSpec.

The spec is the contract between the Python pipeline and Blender; the BLEND and FBX exporters both consume it.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from medverse.geometry.meshio import write_ply_binary

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12}
SOURCE_LABEL = {"bodyparts3d": "BodyParts3D", "brainnetome": "Human Brainnetome"}


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")


def spine_code(label: str) -> str:
    l = label.lower()
    if l == "atlas":
        return "C1"
    if l == "axis" or l.endswith(" of axis"):
        return "C2"
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\b", l):
            for key, pre in (("cervical", "C"), ("thoracic", "T"), ("lumbar", "L")):
                if key in l:
                    return f"{pre}{n}"
    return "S" if l == "sacrum" else ""


def _order(d):
    code = spine_code(d.label)
    k = ({"C": 0, "T": 1, "L": 2, "S": 3}[code[0]], int(code[1:] or 0)) if code else (9, 0)
    return (d.system, d.group, k, d.label, d.entity_id)


def object_name(d, ordinal: int, side_hint: str) -> str:
    base = sanitize(d.label)
    code = spine_code(d.label)
    if d.source == "brainnetome":
        return f"BN_{d.entity_id.split(':')[1]}_{base}"
    if code and d.group == "VERTEBRAE" and not base.startswith(code):
        base = f"{code}_{base}"
    if side_hint and not re.search(r"(^|_)(left|right)(_|$)", base.lower()):
        base = f"{base}_{side_hint}"
    return f"{base}__{d.entity_id.split(':')[1]}"


def build_spec(cfg: dict, meshes: dict, decisions: dict, landmarks: dict, out_dir, centered_note: dict) -> dict:
    """meshes: {entity_id: MeshAsset} in the final world frame (mm), already centered."""
    sc = cfg["scene"]
    out_dir = Path(out_dir)
    mesh_dir = out_dir / "scene" / "meshes"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    objects, collections = [], set()
    items = sorted(((decisions[e], m) for e, m in meshes.items()), key=lambda t: _order(t[0]))
    for i, (d, m) in enumerate(items, 1):
        side = d.side
        if not side and d.source == "bodyparts3d":
            cx = m.vertices[:, 0].mean()
            side = "R" if cx > 1.0 else "L" if cx < -1.0 else ""
            if len([1 for x, _ in items if x.label == d.label]) <= 1:
                side = ""
        name = object_name(d, i, side)
        path = d.system and [d.system] or []
        if d.source == "brainnetome" and d.group == "CEREBRAL_CORTEX":
            coll = [d.system or "BRAIN", "CEREBRAL_CORTEX_BRAINNETOME",
                    {"L": "BN_LEFT_HEMISPHERE", "R": "BN_RIGHT_HEMISPHERE"}.get(d.side, "")]
        elif d.source == "brainnetome":
            coll = [d.system or "BRAIN", f"{d.collection or d.group}_BRAINNETOME"]
        else:
            coll = [d.system or "BRAIN", d.collection or d.group]
        coll = [c for c in coll if c]
        for k in range(1, len(coll) + 1):
            collections.add(tuple(coll[:k]))
        rel = f"{i:03d}_{sanitize(name)[:80]}.ply"
        write_ply_binary(str(mesh_dir / rel), m.vertices, m.faces)
        if d.source == "brainnetome" and "color" in m.metadata:
            rgba = [c / 255.0 for c in m.metadata["color"]] + [1.0]
        else:
            rgba = list(sc["colors"].get(d.group, [0.8, 0.8, 0.8, 1.0]))
        objects.append({
            "name": name, "file": f"scene/meshes/{rel}", "collection": coll, "rgba": rgba,
            "material": f"{d.source}:{d.group}:{d.semantic_subcategory or 'all'}" if d.source != "brainnetome"
                        else f"brainnetome:{d.entity_id.split(':')[1]}",
            "props": {"source": SOURCE_LABEL.get(d.source, d.source), "entity_id": d.entity_id, "group": d.group,
                      "semantic_category": d.semantic_category, "semantic_subcategory": d.semantic_subcategory,
                      "side": side, "ontology_ids": ",".join(d.ontology_ids), "selection_rule": d.rule,
                      "sha256": m.provenance.sha256 if m.provenance else ""},
            "vertices": int(len(m.vertices)), "faces": int(len(m.faces)),
        })
    helpers = [{"name": f"LM_{src}_{k}", "location_mm": np.asarray(v).tolist()}
               for src, lms in sorted(landmarks.items()) for k, v in sorted(lms.items())]
    return {
        "schema": 1, "root_name": sc["root_name"], "units_per_mm": sc["units_per_mm"],
        "material_prefix": sc["material_prefix"], "clean_scene": sc["clean_scene"],
        "viewport": {"shading": sc["viewport_shading"], "euler_deg": sc["viewport_euler_deg"],
                     "distance_factor": sc["viewport_distance_factor"], "hide_grid": sc["hide_grid"]},
        "collections": sorted([list(c) for c in collections], key=lambda c: (len(c), c)),
        "objects": objects, "helpers": helpers, "frame": centered_note,
    }

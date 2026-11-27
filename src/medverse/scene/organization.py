"""Scene organization (pure python, no bpy): turns final assets + decisions into a SceneSpec.

The spec is the contract between the Python pipeline and Blender; the BLEND, FBX, and GLB exporters
all consume it. Source display names, naming prefixes, collection suffixes, and material consolidation
are driven by config hooks so adding a new dataset requires zero edits to scene/.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from medverse.geometry.meshio import write_ply_binary

ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}

# Anatomical lobe/region palette for VR draw-call consolidation (material_mode = "lobe_palette").
# Collapses 246 individual Brainnetome materials into 10 distinct, visually legible standard materials
# that work out-of-the-box in Unity URP/Standard, Blender, and Three.js without custom shaders.
LOBE_PALETTE: dict[str, tuple[str, list[float]]] = {
    "frontal": ("lobe_frontal", [0.85, 0.42, 0.40, 1.0]),
    "temporal": ("lobe_temporal", [0.35, 0.68, 0.56, 1.0]),
    "parietal": ("lobe_parietal", [0.36, 0.56, 0.84, 1.0]),
    "insular": ("lobe_insular", [0.84, 0.64, 0.30, 1.0]),
    "limbic": ("lobe_limbic", [0.68, 0.44, 0.78, 1.0]),
    "occipital": ("lobe_occipital", [0.32, 0.72, 0.78, 1.0]),
    "hippocampus": ("subcortical_hippocampus", [0.86, 0.56, 0.24, 1.0]),
    "amygdala": ("subcortical_amygdala", [0.82, 0.34, 0.52, 1.0]),
    "basal_ganglia": ("subcortical_basal_ganglia", [0.54, 0.46, 0.78, 1.0]),
    "thalamus": ("subcortical_thalamus", [0.46, 0.68, 0.42, 1.0]),
}

_LOBE_RULES = (
    ("frontal", re.compile(r"^(sfg|mfg|ifg|org|prg|pcl|a8|a9|a10|a11|a12|a13|a14|a44|a45|a46|a4|a6|ifj|ifs)", re.I)),
    ("temporal", re.compile(r"^(stg|mtg|itg|fug|phg|psts|a20|a21|a22|a37|a38|a41|a42|ti|tl|th|te|sts)", re.I)),
    ("parietal", re.compile(r"^(spl|ipl|pcun|pog|a1|a2|a3|a5|a7|a39|a40)", re.I)),
    ("insular", re.compile(r"^(ins|g|via|dia|vla|dla|vig|dig)", re.I)),
    ("limbic", re.compile(r"^(cg|a23|a24|a32)", re.I)),
    ("occipital", re.compile(r"^(mvocc|locc|clingu|rling|cun|v5|mocc|lsocc|iopg|msocc)", re.I)),
)


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


def object_name(d, ordinal: int, side_hint: str, scfg: dict | None = None) -> str:
    scfg = scfg or {}
    base = sanitize(d.label)
    code = spine_code(d.label)
    prefix = scfg.get("name_prefix", "")
    local_id = d.entity_id.split(":", 1)[1] if ":" in d.entity_id else d.entity_id
    if prefix:
        return f"{prefix}_{local_id}_{base}"
    if code and d.group == "VERTEBRAE" and not base.startswith(code):
        base = f"{code}_{base}"
    if side_hint and not re.search(r"(^|_)(left|right)(_|$)", base.lower()):
        base = f"{base}_{side_hint}"
    return f"{base}__{local_id}"


def _classify_lobe_palette(d, m) -> tuple[str, list[float]] | None:
    """Assign an atlas region to a compact anatomical lobe/subcortical palette material."""
    if d.semantic_category in LOBE_PALETTE:
        return LOBE_PALETTE[d.semantic_category]
    label = d.label or ""
    for key, rx in _LOBE_RULES:
        if rx.search(label):
            return LOBE_PALETTE[key]
    # Fallback by Brainnetome region ID ranges (Fan et al. 2016: 1-68 Frontal, 69-124 Temporal,
    # 125-162 Parietal, 163-174 Insular, 175-188 Limbic, 189-210 Occipital)
    rid = m.metadata.get("region_id")
    if isinstance(rid, int):
        if 1 <= rid <= 68:
            return LOBE_PALETTE["frontal"]
        if 69 <= rid <= 124:
            return LOBE_PALETTE["temporal"]
        if 125 <= rid <= 162:
            return LOBE_PALETTE["parietal"]
        if 163 <= rid <= 174:
            return LOBE_PALETTE["insular"]
        if 175 <= rid <= 188:
            return LOBE_PALETTE["limbic"]
        if 189 <= rid <= 210:
            return LOBE_PALETTE["occipital"]
    return None


def _resolve_material(d, m, sc: dict, scfg: dict) -> tuple[str, list[float]]:
    mode = sc.get("material_mode", "per_region")
    default_rgba = list(sc["colors"].get(d.group, [0.8, 0.8, 0.8, 1.0]))

    if mode == "group":
        return f"group:{d.group}", default_rgba

    if mode == "lobe_palette":
        if "region_id" in m.metadata or "color" in m.metadata:
            bucket = _classify_lobe_palette(d, m)
            if bucket is not None:
                return f"palette:{bucket[0]}", list(bucket[1])
        return f"group:{d.group}", default_rgba

    # Default / desktop high-fidelity "per_region" mode
    if "color" in m.metadata:
        rgba = [c / 255.0 for c in m.metadata["color"]] + [1.0]
        local_id = d.entity_id.split(":", 1)[1] if ":" in d.entity_id else d.entity_id
        return f"{d.source}:{local_id}", rgba
    return f"{d.source}:{d.group}:{d.semantic_subcategory or 'all'}", default_rgba


def build_spec(cfg: dict, meshes: dict, decisions: dict, landmarks: dict, out_dir, centered_note: dict) -> dict:
    """meshes: {entity_id: MeshAsset} in the final world frame (mm), already centered."""
    sc = cfg["scene"]
    sources_cfg = cfg.get("sources", {})
    out_dir = Path(out_dir)
    mesh_dir = out_dir / "scene" / "meshes"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    objects, collections, unique_materials = [], set(), set()
    items = sorted(((decisions[e], m) for e, m in meshes.items()), key=lambda t: _order(t[0]))
    label_counts: dict[str, int] = {}
    for x, _ in items:
        label_counts[x.label] = label_counts.get(x.label, 0) + 1

    for i, (d, m) in enumerate(items, 1):
        scfg = sources_cfg.get(d.source, {}) if isinstance(sources_cfg.get(d.source), dict) else {}
        side = d.side
        if not side and scfg.get("infer_side_from_x", False):
            cx = float(m.vertices[:, 0].mean())
            if label_counts.get(d.label, 0) > 1:
                side = "R" if cx > 1.0 else "L" if cx < -1.0 else ""

        name = object_name(d, i, side, scfg)
        suffix = scfg.get("collection_suffix", "")
        hemi_groups = set(scfg.get("hemisphere_groups", []))
        prefix = scfg.get("name_prefix", "")
        if d.group in hemi_groups:
            hemi_prefix = f"{prefix}_" if prefix else ""
            hemi_coll = {"L": f"{hemi_prefix}LEFT_HEMISPHERE", "R": f"{hemi_prefix}RIGHT_HEMISPHERE"}.get(side, "")
            coll = [d.system or "BRAIN", f"{d.collection or d.group}{suffix}", hemi_coll]
        else:
            coll = [d.system or "BRAIN", f"{d.collection or d.group}{suffix}"]
        coll = [c for c in coll if c]
        for k in range(1, len(coll) + 1):
            collections.add(tuple(coll[:k]))

        rel = f"{i:03d}_{sanitize(name)[:80]}.ply"
        write_ply_binary(str(mesh_dir / rel), m.vertices, m.faces)
        mat_key, rgba = _resolve_material(d, m, sc, scfg)
        unique_materials.add(mat_key)

        display_source = scfg.get("display_name") or d.source
        props: dict[str, object] = {
            # Canonical v0.2 metadata contract
            "source": display_source,
            "entity_id": d.entity_id,
            "label": d.label,
            "group": d.group,
            "side": side,
            "semantic_category": d.semantic_category,
            "semantic_subcategory": d.semantic_subcategory,
            "ontology_ids": ",".join(d.ontology_ids),
            "selection_rule": d.rule,
            "sha256": m.provenance.sha256 if m.provenance else "",
            # Backward-compatible aliases for medverse-3d-viewer (v1 -> v0.2 transition)
            "bp3d_group": d.group,
            "hemisphere": side,
        }
        if "region_id" in m.metadata:
            props["bn_region_id"] = int(m.metadata["region_id"])
            props["bn_region_name"] = d.label

        objects.append({
            "name": name,
            "file": f"scene/meshes/{rel}",
            "collection": coll,
            "rgba": rgba,
            "material": mat_key,
            "props": props,
            "vertices": int(len(m.vertices)),
            "faces": int(len(m.faces)),
        })

    helpers = [
        {"name": f"LM_{src}_{k}", "location_mm": np.asarray(v).tolist()}
        for src, lms in sorted(landmarks.items())
        for k, v in sorted(lms.items())
    ]
    return {
        "schema": 2,
        "root_name": sc["root_name"],
        "units_per_mm": sc["units_per_mm"],
        "material_prefix": sc["material_prefix"],
        "material_mode": sc.get("material_mode", "per_region"),
        "material_count": len(unique_materials),
        "clean_scene": sc["clean_scene"],
        "viewport": {
            "shading": sc["viewport_shading"],
            "euler_deg": sc["viewport_euler_deg"],
            "distance_factor": sc["viewport_distance_factor"],
            "hide_grid": sc["hide_grid"],
        },
        "collections": sorted([list(c) for c in collections], key=lambda c: (len(c), c)),
        "objects": objects,
        "helpers": helpers,
        "frame": centered_note,
    }

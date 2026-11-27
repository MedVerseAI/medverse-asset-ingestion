"""Report writers and canonical manifest generator.

All writers are cheap, atomic, and idempotent so the pipeline can call them after every stage.
One canonical `manifest.json` unifies v0.2's in-memory ontology & geometry metadata with PR #10's
deterministic output file inventory (relative_path, size_bytes, sha256).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from medverse import __version__
from medverse.config import snapshot
from medverse.reporting.diagnostics import atomic_write_json
from medverse.validation.files import sha256_of

CANONICAL_MANIFEST_SCHEMA = "2.0.0"
QUEST3_HARD_TRIANGLE_CEILING = 180000

SELECTION_COLUMNS = [
    "entity_id", "source", "label", "side", "semantic_category", "semantic_subcategory", "scope",
    "decision", "rule", "matched_target", "group", "fallback_used", "reason", "ontology_ids",
]


def write_selection_review(path, decisions) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SELECTION_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for d in decisions:
            row = d.to_dict() if hasattr(d, "to_dict") else dict(d)
            row["ontology_ids"] = ";".join(row.get("ontology_ids") or [])
            w.writerow(row)
    tmp.replace(path)


def build_canonical_manifest(
    cfg: dict,
    out_dir: Path | str,
    decisions: list,
    meshes: dict,
    exports: dict,
    spec_path: Path | str | None = None,
) -> dict:
    """Build one canonical deterministic manifest.json covering all included entities and final outputs."""
    out_root = Path(out_dir).resolve()
    final_dir = out_root / "final"
    spec_objects: dict[str, dict] = {}
    material_count = 0
    if spec_path and Path(spec_path).is_file():
        spec_data = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        material_count = int(spec_data.get("material_count", 0))
        for obj in spec_data.get("objects", []):
            eid = obj.get("props", {}).get("entity_id")
            if eid:
                spec_objects[eid] = obj

    dec_by_id = {d.entity_id: d for d in decisions}
    entities: list[dict] = []
    materials_seen: set[str] = set()
    total_vertices = 0
    total_triangles = 0

    for eid in sorted(meshes):
        d = dec_by_id.get(eid)
        if d is None or d.decision != "included":
            continue
        m = meshes[eid]
        verts = int(len(m.vertices)) if m.vertices is not None else 0
        tris = int(len(m.faces)) if m.faces is not None else 0
        total_vertices += verts
        total_triangles += tris
        sobj = spec_objects.get(eid, {})
        mat_name = sobj.get("material", "")
        if mat_name:
            materials_seen.add(mat_name)
        entry = {
            "entity_id": eid,
            "object_name": sobj.get("name", d.label),
            "source": d.source,
            "label": d.label,
            "group": d.group,
            "side": sobj.get("props", {}).get("side", d.side),
            "semantic_category": d.semantic_category,
            "semantic_subcategory": d.semantic_subcategory,
            "ontology_ids": list(d.ontology_ids),
            "material": mat_name,
            "vertices": verts,
            "triangles": tris,
            "source_sha256": m.provenance.sha256 if m.provenance else "",
        }
        if "region_id" in m.metadata:
            entry["bn_region_id"] = int(m.metadata["region_id"])
        entities.append(entry)

    outputs: list[dict] = []
    for fmt_name in sorted(exports):
        rec = exports[fmt_name]
        if not isinstance(rec, dict) or rec.get("status") != "ok":
            continue
        fpath_str = rec.get("file")
        if not fpath_str:
            continue
        fpath = Path(fpath_str).resolve()
        if not fpath.is_file():
            continue
        try:
            rel_path = fpath.relative_to(final_dir).as_posix()
        except ValueError:
            try:
                rel_path = fpath.relative_to(out_root).as_posix()
            except ValueError:
                rel_path = fpath.name
        outputs.append({
            "name": fmt_name,
            "format": fpath.suffix.lstrip(".").lower() or fmt_name,
            "relative_path": rel_path,
            "size_bytes": int(fpath.stat().st_size),
            "sha256": sha256_of(fpath),
            "meshes": int(rec.get("reimported_meshes", rec.get("reopened_meshes", rec.get("exported_meshes", len(entities))))),
            "triangles": int(rec.get("reimported_triangles", rec.get("triangles", total_triangles))),
            "materials": int(rec.get("reimported_materials", rec.get("materials", material_count or len(materials_seen)))),
        })

    scene_budget = int(cfg.get("geometry", {}).get("scene_triangle_budget", 0))
    return {
        "schema_version": CANONICAL_MANIFEST_SCHEMA,
        "pipeline_version": __version__,
        "profile": cfg.get("profile", {}).get("name", ""),
        "config_sha256": snapshot(cfg)["sha256"],
        "summary": {
            "total_entities": len(entities),
            "total_outputs": len(outputs),
            "total_vertices": total_vertices,
            "total_triangles": total_triangles,
            "total_materials": material_count or len(materials_seen),
            "scene_triangle_budget": scene_budget,
            "quest3_ceiling_triangles": QUEST3_HARD_TRIANGLE_CEILING,
            "within_quest3_budget": total_triangles < QUEST3_HARD_TRIANGLE_CEILING,
        },
        "outputs": outputs,
        "entities": entities,
    }


def write_canonical_manifest(path: Path | str, manifest: dict) -> Path:
    out = Path(path)
    atomic_write_json(out, manifest)
    return out


class Reports:
    """Owner of the report files of a run."""
    NAMES = {
        "pipeline": "pipeline_report.json",
        "selection": "selection_review.csv",
        "assets": "asset_manifest.json",
        "manifest": "manifest.json",
        "transforms": "transform_manifest.json",
        "geometry": "geometry_report.json",
        "registration": "registration_report.json",
        "export": "export_report.json",
        "diagnostics": "diagnostics.log",
    }

    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.dir = self.out_dir / "reports"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.dir / self.NAMES[key]

    def json(self, key: str, obj) -> None:
        atomic_write_json(self.path(key), obj)

    def selection(self, decisions) -> None:
        write_selection_review(self.path("selection"), decisions)

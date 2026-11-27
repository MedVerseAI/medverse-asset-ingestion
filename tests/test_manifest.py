"""Unit tests for the unified canonical manifest.json builder (ontology + mesh stats + output SHA-256)."""
from __future__ import annotations

import json

import numpy as np

import conftest  # noqa: F401
from medverse.config import load_config
from medverse.core.assets import MeshAsset, Provenance
from medverse.reporting.manifest import (
    CANONICAL_MANIFEST_SCHEMA,
    build_canonical_manifest,
    write_canonical_manifest,
)
from medverse.selection.rules import Decision
from medverse.validation import sha256_of


def test_canonical_manifest_deterministic_sha256_and_all_entities(tmp_path):
    out_dir = tmp_path / "run"
    final_dir = out_dir / "final"
    final_dir.mkdir(parents=True)

    fbx = final_dir / "anatomical_model_quest3_lod0.fbx"
    glb = final_dir / "anatomical_model_quest3_lod0.glb"
    fbx.write_bytes(b"mock-fbx-binary-payload")
    glb.write_bytes(b"mock-glb-binary-payload")

    cfg = load_config(profile="quest3_lod0")

    decisions = [
        Decision(
            entity_id="brainnetome:001",
            source="brainnetome",
            label="SFG_L_7_1",
            side="L",
            semantic_category="cerebral_cortex",
            semantic_subcategory="",
            scope="all",
            decision="included",
            rule="include_semantic_target",
            matched_target="cerebral_cortex",
            group="CEREBRAL_CORTEX",
            system="BRAIN",
            collection="CEREBRAL_CORTEX",
            ontology_ids=("BN001",),
        ),
        Decision(
            entity_id="brainnetome:002",
            source="brainnetome",
            label="SFG_R_7_1",
            side="R",
            semantic_category="cerebral_cortex",
            semantic_subcategory="",
            scope="all",
            decision="included",
            rule="include_semantic_target",
            matched_target="cerebral_cortex",
            group="CEREBRAL_CORTEX",
            system="BRAIN",
            collection="CEREBRAL_CORTEX",
            ontology_ids=("BN002",),
        ),
        Decision(
            entity_id="bodyparts3d:FJ3413",
            source="bodyparts3d",
            label="cerebellum",
            side="",
            semantic_category="cerebellum",
            semantic_subcategory="",
            scope="brain",
            decision="included",
            rule="include_semantic_target",
            matched_target="cerebellum",
            group="CEREBELLUM",
            system="BRAIN",
            collection="CEREBELLUM",
            ontology_ids=("FMA67944",),
        ),
        Decision(
            entity_id="bodyparts3d:FJ9999",
            source="bodyparts3d",
            label="reference_gyrus",
            side="L",
            semantic_category="cerebral_cortex",
            decision="reference",
            rule="owned_by_other_source",
        ),
    ]

    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    f = np.array([[0, 1, 2]], dtype=np.int64)
    meshes = {
        "brainnetome:001": MeshAsset("brainnetome:001", "brainnetome", vertices=v, faces=f,
                                     provenance=Provenance("brainnetome", "atlas.nii.gz", "a" * 64),
                                     metadata={"region_id": 1}),
        "brainnetome:002": MeshAsset("brainnetome:002", "brainnetome", vertices=v, faces=f,
                                     provenance=Provenance("brainnetome", "atlas.nii.gz", "a" * 64),
                                     metadata={"region_id": 2}),
        "bodyparts3d:FJ3413": MeshAsset("bodyparts3d:FJ3413", "bodyparts3d", vertices=v, faces=f,
                                        provenance=Provenance("bodyparts3d", "FJ3413.obj", "b" * 64)),
        "bodyparts3d:FJ9999": MeshAsset("bodyparts3d:FJ9999", "bodyparts3d", vertices=v, faces=f),
    }

    exports = {
        "fbx": {"status": "ok", "file": str(fbx), "reimported_meshes": 3, "reimported_triangles": 3, "reimported_materials": 2},
        "glb": {"status": "ok", "file": str(glb), "reimported_meshes": 3, "reimported_triangles": 3, "reimported_materials": 2},
        "blend": {"status": "skipped", "reason": "disabled"},
    }

    m1 = build_canonical_manifest(cfg, out_dir, decisions, meshes, exports)
    m2 = build_canonical_manifest(cfg, out_dir, decisions, meshes, exports)
    assert m1 == m2  # deterministic

    out_file = write_canonical_manifest(final_dir / "manifest.json", m1)
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written == m1
    assert written["schema_version"] == CANONICAL_MANIFEST_SCHEMA
    # Reference-only entity excluded; both Brainnetome regions preserved (no [:1] truncation)
    assert written["summary"]["total_entities"] == 3
    assert written["summary"]["total_outputs"] == 2
    assert written["summary"]["total_triangles"] == 3
    assert written["summary"]["within_quest3_budget"] is True

    by_fmt = {o["format"]: o for o in written["outputs"]}
    assert by_fmt["fbx"]["sha256"] == sha256_of(fbx)
    assert by_fmt["fbx"]["size_bytes"] == fbx.stat().st_size
    assert by_fmt["fbx"]["relative_path"] == "anatomical_model_quest3_lod0.fbx"
    assert by_fmt["glb"]["sha256"] == sha256_of(glb)

    by_eid = {e["entity_id"]: e for e in written["entities"]}
    assert set(by_eid) == {"brainnetome:001", "brainnetome:002", "bodyparts3d:FJ3413"}
    assert by_eid["brainnetome:001"]["bn_region_id"] == 1
    assert by_eid["brainnetome:002"]["bn_region_id"] == 2
    assert by_eid["bodyparts3d:FJ3413"]["ontology_ids"] == ["FMA67944"]

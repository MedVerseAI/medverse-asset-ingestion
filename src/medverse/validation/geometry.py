"""Geometry validation of the final mesh assets (finite, indexable, plausible size, no exact duplicates)."""
from __future__ import annotations

import hashlib

import numpy as np

from medverse.validation import Checks


def validate_geometry(meshes: dict) -> dict:
    """meshes: {asset_id: MeshAsset} (final, scene frame, mm)."""
    c = Checks()
    bad_finite, bad_index, empty, huge, tiny, open_m = [], [], [], [], [], []
    seen = {}
    dup = []
    for aid, m in meshes.items():
        v, f = m.vertices, m.faces
        if len(v) == 0 or len(f) == 0:
            empty.append(aid)
            continue
        if not np.isfinite(v).all():
            bad_finite.append(aid)
        if f.min() < 0 or f.max() >= len(v):
            bad_index.append(aid)
        ext = v.max(0) - v.min(0)
        if ext.max() > 2000.0:
            huge.append(aid)
        if ext.max() < 0.5:
            tiny.append(aid)
        if not m.metadata.get("closed", True):
            open_m.append(aid)
        h = hashlib.sha1(np.round(v, 3).tobytes()).hexdigest()
        if h in seen:
            dup.append((aid, seen[h]))
        seen[h] = aid
    c.check("meshes_not_empty", not empty, f"empty meshes: {empty[:10]}")
    c.check("vertices_finite", not bad_finite, f"non-finite vertices: {bad_finite[:10]}")
    c.check("face_indices_valid", not bad_index, f"bad face indices: {bad_index[:10]}")
    c.check("extent_plausible_mm", not huge and not tiny,
            f"implausible extents (units wrong?) huge={huge[:5]} tiny={tiny[:5]}")
    c.check("no_exact_duplicate_geometry", not dup, f"identical geometry: {dup[:10]}", level="fail")
    c.check("watertight", not open_m, f"{len(open_m)} open (non-watertight) meshes (info only)", level="warn")
    r = c.result()
    r["counts"] = {"meshes": len(meshes), "open": len(open_m)}
    return r

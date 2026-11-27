"""Mesh cleanup, per-mesh decimation, and global scene triangle budgeting."""
from __future__ import annotations

import numpy as np

try:                                            # optional dependency (required for quest3_lod0)
    import fast_simplification
except Exception:                               # pragma: no cover
    fast_simplification = None


def signed_volume(v, f) -> float:
    if len(f) == 0:
        return 0.0
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def is_closed(f) -> bool:
    if len(f) == 0:
        return False
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e.sort(axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def clean_mesh(verts, faces, weld_tol, min_faces=50, min_fraction=0.005):
    """Weld, drop degenerate/duplicate faces and tiny islands, fix inverted closed meshes. -> (v, f, stats)"""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    stats = {"raw_verts": int(len(verts)), "raw_faces": int(len(faces))}
    q = np.round(verts / weld_tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    verts = verts[first]
    faces = inv.reshape(-1)[faces]
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    stats["degenerate"] = int((~ok).sum())
    faces = faces[ok]
    key = np.sort(faces, axis=1)
    _, keep = np.unique(key, axis=0, return_index=True)
    stats["duplicate"] = int(len(faces) - len(keep))
    faces = faces[np.sort(keep)]
    n = len(verts)
    if len(faces):
        a = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
        b = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
        g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
        ncomp, lab = connected_components(g, directed=False)
        fcount = np.bincount(lab[faces[:, 0]], minlength=ncomp)
        tot = fcount.sum()
        small = (fcount < min_faces) & (fcount < min_fraction * tot)
        if small.all():
            small[np.argmax(fcount)] = False
        stats["components"], stats["islands_removed"] = int(ncomp), int(small.sum())
        faces = faces[~small[lab[faces[:, 0]]]]
    else:
        stats["components"], stats["islands_removed"] = 0, 0
    used = np.unique(faces)
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    verts, faces = verts[used], remap[faces]
    vol = signed_volume(verts, faces)
    stats["closed"] = is_closed(faces)
    stats["flipped"] = False
    if stats["closed"] and vol < 0:
        faces = faces[:, ::-1].copy()
        stats["flipped"] = True
        vol = -vol
    stats["volume"] = float(vol)
    return verts, faces, stats


def decimate(verts, faces, budget, aggressiveness=5, max_drift=1.0, require_simplification=False):
    """-> (verts, faces, decimated?, note).

    Fails loudly when ``require_simplification=True`` and ``fast_simplification`` is missing;
    otherwise returns an explicit warning note instead of silently skipping.
    """
    if budget is None or budget <= 0 or len(faces) <= budget:
        return verts, faces, False, ""
    if fast_simplification is None:
        msg = (
            "fast_simplification is not installed; cannot decimate "
            f"{len(faces)} faces to budget {budget} (install `pip install fast-simplification`)"
        )
        if require_simplification:
            raise RuntimeError(msg)
        return verts, faces, False, f"WARNING: {msg}"
    red = min(max(1.0 - budget / float(len(faces)), 0.0), 0.995)
    try:
        v2, f2 = fast_simplification.simplify(
            verts.astype(np.float64),
            faces.astype(np.int64),
            target_reduction=red,
            agg=aggressiveness,
        )
    except Exception as exc:
        return verts, faces, False, f"decimation failed ({exc})"
    if len(v2) == 0 or len(f2) == 0:
        return verts, faces, False, "decimation rejected (empty mesh produced)"
    drift = max(np.abs(v2.min(0) - verts.min(0)).max(), np.abs(v2.max(0) - verts.max(0)).max())
    if drift > max_drift:
        return verts, faces, False, f"decimation rejected (bbox drift {drift:.2f} mm > {max_drift:.2f} mm)"
    return v2, f2.astype(np.int64), True, ""


def enforce_scene_budget(
    meshes: dict,
    included_ids: list[str],
    scene_budget: int,
    min_faces_per_mesh: int = 80,
    aggressiveness: int = 7,
    max_drift: float = 2.5,
    require_simplification: bool = False,
) -> dict:
    """Enforce a global scene-wide triangle ceiling across all included meshes.

    Proportionally scales down meshes above ``min_faces_per_mesh`` so total scene triangles
    stay strictly within ``scene_budget`` (e.g., < 180,000 for Meta Quest 3).
    """
    ids = [eid for eid in included_ids if eid in meshes]
    total_before = sum(len(meshes[eid].faces) for eid in ids)
    summary = {
        "applied": False,
        "scene_budget": int(scene_budget),
        "total_before": int(total_before),
        "total_after": int(total_before),
        "meshes_decimated": 0,
        "within_budget": scene_budget <= 0 or total_before <= scene_budget,
        "warnings": [],
    }
    if scene_budget <= 0 or total_before <= scene_budget or not ids:
        return summary

    if fast_simplification is None:
        msg = (
            f"Scene has {total_before:,} triangles (budget {scene_budget:,}), "
            "but fast_simplification is not installed"
        )
        if require_simplification:
            raise RuntimeError(msg)
        summary["warnings"].append(msg)
        return summary

    decimated_ids = set()
    # Two progressive passes: pass 1 uses configured params; pass 2 tightens slightly if still over budget.
    for pass_idx, (safety_ratio, agg_bump, drift_mult) in enumerate(((0.95, 0, 1.0), (0.90, 2, 2.0)), 1):
        current_total = sum(len(meshes[eid].faces) for eid in ids)
        if current_total <= scene_budget:
            break
        target_total = int(scene_budget * safety_ratio)
        floor_sum = sum(min(len(meshes[eid].faces), min_faces_per_mesh) for eid in ids)
        excess_available = sum(max(0, len(meshes[eid].faces) - min_faces_per_mesh) for eid in ids)
        excess_allowed = max(0, target_total - floor_sum)
        scale = (excess_allowed / excess_available) if excess_available > 0 else 0.0

        for eid in ids:
            m = meshes[eid]
            n_faces = len(m.faces)
            if n_faces <= min_faces_per_mesh:
                continue
            target_faces = max(min_faces_per_mesh, int(min_faces_per_mesh + (n_faces - min_faces_per_mesh) * scale))
            if target_faces >= n_faces:
                continue
            v2, f2, ok, note = decimate(
                m.vertices,
                m.faces,
                target_faces,
                aggressiveness=min(aggressiveness + agg_bump, 9),
                max_drift=max_drift * drift_mult,
                require_simplification=require_simplification,
            )
            if ok and len(f2) < n_faces:
                m.vertices, m.faces = v2, f2
                decimated_ids.add(eid)
                st = m.metadata.setdefault("stats", {})
                st["scene_budget_decimated"] = True
                st["scene_budget_pass"] = pass_idx
            elif note:
                summary["warnings"].append(f"{eid}: {note}")

    total_after = sum(len(meshes[eid].faces) for eid in ids)
    summary.update(
        applied=True,
        total_after=int(total_after),
        meshes_decimated=len(decimated_ids),
        within_budget=total_after <= scene_budget,
    )
    return summary

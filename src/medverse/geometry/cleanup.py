"""Mesh cleanup + optional decimation (ported 1:1 from the legacy exporter, parameters from config)."""
from __future__ import annotations

import numpy as np

try:                                            # optional dependency
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


def decimate(verts, faces, budget, aggressiveness=5, max_drift=1.0):
    """-> (verts, faces, decimated?, note).  No-op when fast_simplification is missing or under budget."""
    if fast_simplification is None or len(faces) <= budget:
        return verts, faces, False, ""
    red = 1.0 - budget / float(len(faces))
    try:
        v2, f2 = fast_simplification.simplify(verts.astype(np.float64), faces.astype(np.int64),
                                              target_reduction=red, agg=aggressiveness)
    except Exception as exc:
        return verts, faces, False, f"decimation failed ({exc})"
    drift = max(np.abs(v2.min(0) - verts.min(0)).max(), np.abs(v2.max(0) - verts.max(0)).max())
    if drift > max_drift:
        return verts, faces, False, f"decimation rejected (bbox drift {drift:.2f})"
    return v2, f2.astype(np.int64), True, ""

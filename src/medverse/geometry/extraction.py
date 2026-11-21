"""Surface extraction: VolumeAsset (label volume) -> MeshAsset.  Decided HERE, never by the core engine."""
from __future__ import annotations

import numpy as np

from medverse.core.assets import CoordinateSystem, MeshAsset, Provenance


class NoSurface(Exception):
    """Region too small / empty to produce a surface (recorded as a per-entity skip, not a failure)."""


def _crop_box(mask, margin):
    idx = np.argwhere(mask)
    lo = np.maximum(idx.min(axis=0) - margin, 0)
    hi = np.minimum(idx.max(axis=0) + 1 + margin, mask.shape)
    return lo, hi


def extract_region_surface(volume, label_id: int, smooth_sigma: float, min_voxels: int) -> MeshAsset:
    """Marching cubes on one label of `volume`.  Vertices are mapped through the volume's affine (kept untouched)."""
    from scipy.ndimage import gaussian_filter
    from skimage.measure import marching_cubes

    mask = volume.data == label_id
    n = int(mask.sum())
    if n < min_voxels:
        raise NoSurface(f"region {label_id}: only {n} voxels (< {min_voxels})")
    margin = int(np.ceil(3 * smooth_sigma)) + 1
    lo, hi = _crop_box(mask, margin)
    sub = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    vol = np.pad(sub.astype(np.float32), 1)
    if smooth_sigma > 0:
        vol = gaussian_filter(vol, smooth_sigma)
    try:
        verts, faces, _, _ = marching_cubes(vol, level=0.5)
    except (ValueError, RuntimeError) as exc:
        raise NoSurface(f"region {label_id}: no surface ({exc})")
    verts = verts - 1 + lo                                   # undo padding -> full-volume voxel indices
    A = np.asarray(volume.affine, dtype=float)
    verts = verts @ A[:3, :3].T + A[:3, 3]                   # voxel -> world (affine preserved)
    if np.linalg.det(A[:3, :3]) < 0:
        faces = faces[:, ::-1]
    return MeshAsset(asset_id=volume.asset_id, source=volume.source, vertices=verts.astype(np.float64),
                     faces=faces.astype(np.int64),
                     coordinate_system=CoordinateSystem(name="RAS", units="mm", confidence="metadata",
                                                        notes=["from NIfTI affine"]),
                     provenance=Provenance(volume.source, volume.provenance.path if volume.provenance else "",
                                           volume.provenance.sha256 if volume.provenance else "",
                                           [f"marching cubes label {label_id}, sigma={smooth_sigma}, voxels={n}"]),
                     metadata=dict(volume.metadata, voxels=n, extracted_from="volume"),
                     transform=A.copy())

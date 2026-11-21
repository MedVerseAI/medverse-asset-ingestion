"""Generic asset model: sources are NOT forced into meshes on entry.

BaseAsset -> MeshAsset | VolumeAsset | PointCloudAsset.  Geometry processing decides whether a volume needs
surface extraction; the core engine never does.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class CoordinateSystem:
    name: str = "unknown"            # "RAS" (x=Right,y=Anterior,z=Superior) | "LAS" | "raw" | "unknown"
    units: str = "unknown"           # "mm" | "m" | "unknown"
    inferred: bool = False           # True when derived from geometry rather than file metadata
    confidence: str = "unknown"      # "metadata" | "ok" | "low" | "none"
    notes: list = field(default_factory=list)

    def to_dict(self):
        return dict(name=self.name, units=self.units, inferred=self.inferred, confidence=self.confidence,
                    notes=list(self.notes))


@dataclass
class Provenance:
    source: str
    path: str = ""
    sha256: str = ""
    notes: list = field(default_factory=list)

    def to_dict(self):
        return dict(source=self.source, path=self.path, sha256=self.sha256, notes=list(self.notes))


@dataclass
class BaseAsset:
    asset_id: str
    source: str
    kind: str = "base"
    coordinate_system: CoordinateSystem = field(default_factory=CoordinateSystem)
    transform: np.ndarray = field(default_factory=lambda: np.eye(4))      # cumulative asset -> current frame
    provenance: Provenance = None
    metadata: dict = field(default_factory=dict)

    def manifest(self) -> dict:
        return dict(asset_id=self.asset_id, source=self.source, kind=self.kind,
                    coordinate_system=self.coordinate_system.to_dict(),
                    provenance=self.provenance.to_dict() if self.provenance else None,
                    transform=np.asarray(self.transform).tolist(), metadata=_json_safe(self.metadata))


@dataclass
class MeshAsset(BaseAsset):
    vertices: np.ndarray = None       # (N,3) float64
    faces: np.ndarray = None          # (M,3) int64
    rgb: Optional[np.ndarray] = None  # (3,) uint8 or None
    kind: str = "mesh"

    def apply(self, T: np.ndarray, record_transform: bool = True) -> None:
        """Apply a 4x4 transform to the vertices (mirroring transforms also reverse the winding)."""
        T = np.asarray(T, dtype=float)
        self.vertices = self.vertices @ T[:3, :3].T + T[:3, 3]
        if np.linalg.det(T[:3, :3]) < 0:
            self.faces = self.faces[:, ::-1].copy()
        if record_transform:
            self.transform = T @ self.transform

    def bbox(self):
        return self.vertices.min(0), self.vertices.max(0)


@dataclass
class VolumeAsset(BaseAsset):
    data: np.ndarray = None           # integer label volume or scalar volume
    affine: np.ndarray = None         # voxel -> world (4x4), preserved untouched
    kind: str = "volume"

    def orientation(self) -> str:
        """Axis codes of the voxel grid (direction each voxel axis points to), e.g. 'LAS' for a standard MNI affine."""
        A = np.asarray(self.affine)[:3, :3]
        pos, neg = "RAS", "LPI"
        codes = []
        for col in range(3):
            v = A[:, col]
            ax = int(np.argmax(np.abs(v)))
            codes.append(pos[ax] if v[ax] > 0 else neg[ax])
        return "".join(codes)

    def voxel_size(self):
        return np.linalg.norm(np.asarray(self.affine)[:3, :3], axis=0)


@dataclass
class PointCloudAsset(BaseAsset):
    points: np.ndarray = None         # (N,3)
    kind: str = "pointcloud"


@dataclass
class SourceEntity:
    """One selectable anatomical structure of a source (metadata only; geometry is loaded lazily)."""
    entity_id: str                    # globally unique: "<source>:<local id>"
    source: str
    label: str
    names: frozenset = frozenset()    # every concept name the entity belongs to (lower case)
    own_names: frozenset = frozenset()
    ontology_ids: tuple = ()
    side: str = ""                    # "L" | "R" | ""
    attributes: dict = field(default_factory=dict)
    loader: Optional[Callable[[], Any]] = None

    def brief(self) -> dict:
        return dict(entity_id=self.entity_id, source=self.source, label=self.label, side=self.side,
                    ontology_ids=list(self.ontology_ids), attributes=_json_safe(self.attributes))


def _json_safe(o: Any):
    if isinstance(o, dict):
        return {str(k): _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o

"""Spatial transforms with provenance.  Every applied transform is logged (transform_manifest.json)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def rigid(R=None, t=None, s: float = 1.0) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = (np.eye(3) if R is None else np.asarray(R, dtype=float)) * s
    T[:3, 3] = np.zeros(3) if t is None else np.asarray(t, dtype=float)
    return T


def decompose(T: np.ndarray):
    """-> (scale, R, t) of a similarity transform."""
    A = np.asarray(T)[:3, :3]
    s = float(np.cbrt(abs(np.linalg.det(A)))) or 1.0
    return s, A / s, np.asarray(T)[:3, 3].copy()


def rot_angle_deg(R) -> float:
    c = (np.trace(R) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def rot_from_euler_deg(rx, ry, rz) -> np.ndarray:
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


@dataclass
class TransformRecord:
    transform_id: str
    target: str                       # asset id / "source:<name>" / "group:<g>"
    matrix: np.ndarray
    kind: str                         # "spatial_metadata" | "unit_conversion" | "frame_inference" | "mirror"
                                      # | "landmark" | "reference_geometry" | "icp" | "scale" | "centering" | "scene_units"
    reason: str = ""
    scale: float = 1.0
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return dict(transform_id=self.transform_id, target=self.target, kind=self.kind, reason=self.reason,
                    scale=self.scale, determinant=float(np.linalg.det(np.asarray(self.matrix)[:3, :3])),
                    matrix=np.asarray(self.matrix).tolist(), evidence=self.evidence)


class TransformLog:
    def __init__(self):
        self.records: list[TransformRecord] = []

    def add(self, target, matrix, kind, reason="", evidence=None) -> TransformRecord:
        s = decompose(matrix)[0]
        rec = TransformRecord(f"T{len(self.records) + 1:04d}", target, np.asarray(matrix, dtype=float), kind,
                              reason, s, evidence or {})
        self.records.append(rec)
        return rec

    def to_dict(self):
        return {"transforms": [r.to_dict() for r in self.records],
                "scaled": [r.transform_id for r in self.records
                           if abs(r.scale - 1.0) > 1e-9 and r.kind not in ("spatial_metadata", "scene_units", "unit_conversion")]}

"""Human Brainnetome atlas adapter: label NIfTI (volume) + FreeSurfer-style LUT.

The volume is kept as a VolumeAsset with its affine UNTOUCHED.  Surface extraction is the job of
geometry/extraction.py, not of this adapter or of the core.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

from medverse.adapters.base import SourceAdapter
from medverse.adapters.brainnetome.nifti import load_nifti
from medverse.core.assets import CoordinateSystem, Provenance, SourceEntity, VolumeAsset, sha256_file
from medverse.core.registry import register_adapter


def read_lut(path) -> dict:
    """'index name R G B A' -> {id: (name, (r, g, b))}"""
    lut = {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5 or line.lstrip().startswith("#"):
                continue
            try:
                idx = int(parts[0])
                r, g, b = (int(x) for x in parts[-4:-1])
            except ValueError:
                continue
            lut[idx] = (parts[1], (r, g, b))
    return lut


@register_adapter("brainnetome")
class BrainnetomeAdapter(SourceAdapter):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.root = self._dir("root", self.data_dir / "raw" / "brainnetome")
        self.atlas_path = None
        self.lut_path = None
        self.lut: dict = {}
        self._vol = None                                    # (data, affine, sha)

    def _find(self, fname: str):
        for dp, _, fns in os.walk(self.root):
            if fname in fns:
                return Path(dp) / fname
        return None

    def discover(self) -> dict:
        self.atlas_path = self._find(self.scfg["atlas_file"])
        self.lut_path = self._find(self.scfg["lut_file"])
        problems = []
        if not self.atlas_path:
            problems.append(f"atlas '{self.scfg['atlas_file']}' not found under {self.root}")
        if not self.lut_path:
            problems.append(f"LUT '{self.scfg['lut_file']}' not found under {self.root} (names/colours will be generated)")
        files = [{"path": str(p), "sha256": sha256_file(str(p))} for p in (self.atlas_path, self.lut_path) if p]
        return {"available": bool(self.atlas_path) or bool(self.lut_path), "atlas_found": bool(self.atlas_path),
                "problems": problems, "files": files}

    def _volume(self):
        if self._vol is None:
            if not self.atlas_path:
                self.atlas_path = self._find(self.scfg["atlas_file"])
            if not self.atlas_path:
                raise FileNotFoundError(f"atlas '{self.scfg['atlas_file']}' not found under {self.root}")
            data, affine = load_nifti(self.atlas_path)
            self._vol = (np.rint(data).astype(np.int32), np.asarray(affine, dtype=float),
                         sha256_file(str(self.atlas_path)))
        return self._vol

    def build(self) -> None:
        if self.lut_path is None:
            self.lut_path = self._find(self.scfg["lut_file"])
        self.lut = read_lut(self.lut_path) if self.lut_path else {}
        ids = sorted(i for i in self.lut if i > 0)
        if not ids:                                          # no LUT: ids come from the volume itself
            data, _, _ = self._volume()
            ids = [int(i) for i in np.unique(data) if i > 0]
            self.problems.append("no LUT: region names are generated")
        cmax = self.scfg["cortical_max_id"]
        for rid in ids:
            name, color = self.lut.get(rid, (f"Region_{rid}", (180, 180, 180)))
            m = re.search(r"_([LR])$", name)
            eid = f"brainnetome:{rid:03d}"
            self.ontology.name[f"BN{rid:03d}"] = name
            self.ontology.elements["atlas"][f"BN{rid:03d}"].add(eid)
            self.entities[eid] = SourceEntity(
                entity_id=eid, source=self.name, label=name, names=frozenset({name.lower()}),
                own_names=frozenset({name.lower()}), ontology_ids=(f"BN{rid:03d}",), side=m.group(1) if m else "",
                attributes={"region_id": rid, "cortical": rid <= cmax, "color": list(color)},
                loader=None)
        self.ontology.finalize()
        for e in self.entities.values():
            e.loader = (lambda ent=e: self.load(ent))

    def load(self, entity) -> VolumeAsset:
        data, affine, sha = self._volume()
        return VolumeAsset(
            asset_id=entity.entity_id, source=self.name, data=data, affine=affine,        # shared array, not copied
            coordinate_system=CoordinateSystem(name="RAS", units="mm", inferred=False, confidence="metadata",
                                               notes=["world frame given by the NIfTI affine (RAS+ convention)"]),
            provenance=Provenance(self.name, str(self.atlas_path), sha),
            metadata={"region_id": entity.attributes["region_id"], "label": entity.label,
                      "color": entity.attributes["color"], "side": entity.side})

    # ------------------------------------------------------------------ validation of the volume itself
    def region_centroids_world(self) -> dict:
        data, affine, _ = self._volume()
        ids = [int(i) for i in np.unique(data) if i > 0]
        flat = data.ravel()
        cnt = np.bincount(flat, minlength=int(flat.max()) + 1).astype(float)
        sums = []
        for ax in range(3):
            idx = np.arange(data.shape[ax]).reshape([-1 if a == ax else 1 for a in range(3)])
            sums.append(np.bincount(flat, weights=np.broadcast_to(idx, data.shape).ravel(), minlength=len(cnt)))
        out = {}
        for i in ids:
            vox = np.array([s[i] / cnt[i] for s in sums] + [1.0])
            out[i] = (affine @ vox)[:3]
        return out

    def lr_check(self) -> dict:
        """Does the label side (_L/_R) agree with the affine?  (left hemisphere must lie at -x in RAS)"""
        cen = self.region_centroids_world()
        L = [cen[int(e.attributes["region_id"])][0] for e in self.entities.values()
             if e.side == "L" and e.attributes["region_id"] in cen]
        R = [cen[int(e.attributes["region_id"])][0] for e in self.entities.values()
             if e.side == "R" and e.attributes["region_id"] in cen]
        if not L or not R:
            return {"checked": False, "mismatch": False}
        xl, xr = float(np.mean(L)), float(np.mean(R))
        return {"checked": True, "mean_x_left": xl, "mean_x_right": xr, "mismatch": xl > xr}

    def validate_source(self) -> list:
        data, affine, _ = self._volume()
        warns = []
        n = len([i for i in np.unique(data) if i > 0])
        exp = self.scfg["expected_regions"]
        if n != exp:
            warns.append(f"brainnetome: expected {exp} regions, found {n}")
        det = float(np.linalg.det(affine[:3, :3]))
        self.volume_info = {"shape": list(data.shape), "affine": affine.tolist(), "determinant": det,
                            "voxel_size_mm": np.linalg.norm(affine[:3, :3], axis=0).tolist(),
                            "orientation": VolumeAsset("x", self.name, data=data, affine=affine).orientation(),
                            "regions": n, "lr_check": self.lr_check()}
        return warns

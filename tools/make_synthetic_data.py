"""Synthetic stand-in data (ellipsoids) for end-to-end tests when the real OBJ / NIfTI files are not at hand.
Uses the REAL metadata + LUT.  BodyParts3D meshes are written in a deliberately different raw frame
(centimetres, permuted axes) so unit/frame inference is exercised.   Usage: make_synthetic_data.py <data_dir> [--flip-lr]"""
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from medverse.adapters.brainnetome.nifti import save_nifti          # noqa: E402
from medverse.adapters.bodyparts3d import BodyParts3DAdapter        # noqa: E402
from medverse.adapters.brainnetome import BrainnetomeAdapter        # noqa: E402
from medverse.config import load_config                             # noqa: E402
from medverse.scene.organization import spine_code                  # noqa: E402
from medverse.selection.resolver import SelectionEngine             # noqa: E402


def ellipsoid(c, r, n=14):
    th = np.linspace(0, np.pi, n + 1)[1:-1]
    ph = np.linspace(0, 2 * np.pi, 2 * n, endpoint=False)
    v = [[0, 0, r[2]]] + [[r[0] * np.sin(t) * np.cos(p), r[1] * np.sin(t) * np.sin(p), r[2] * np.cos(t)]
                          for t in th for p in ph] + [[0, 0, -r[2]]]
    v = np.array(v) + c
    f, m = [], len(ph)
    for j in range(m):
        f.append([0, 1 + j, 1 + (j + 1) % m])
    for i in range(len(th) - 1):
        for j in range(m):
            a, b = 1 + i * m + j, 1 + i * m + (j + 1) % m
            f.append([a, a + m, b]); f.append([b, a + m, b + m])
    last = len(v) - 1
    for j in range(m):
        f.append([last, 1 + (len(th) - 1) * m + (j + 1) % m, 1 + (len(th) - 1) * m + j])
    return v, np.array(f)


def write_obj(path, v, f):
    with open(path, "w") as fh:
        for p in v:
            fh.write("v %.5f %.5f %.5f\n" % tuple(p))
        for t in f:
            fh.write("f %d %d %d\n" % tuple(t + 1))


def place(d, idx, n_in_cat, rng):
    s = {"L": -1.0, "R": 1.0}.get(d.side, 0.0)
    cat, lab = d.semantic_category, d.label
    if cat == "vertebra":
        return np.array([0, -35, -70 - 14.5 * idx]), np.array([22, 16, 6.5])
    if cat == "intervertebral_disc":
        return np.array([0, -35, -77 - 14.5 * idx]), np.array([20, 14, 2.5])
    if cat == "spinal_cord":
        return np.array([0, -38, -210]), np.array([5, 5, 190])
    if cat == "cerebellum":
        return np.array([0, -60, -38]), np.array([50, 33, 25])
    if cat == "brainstem":
        return np.array([0, -28, -50 - 1.5 * idx]), np.array([13, 12, 14])
    if cat == "cerebral_cortex":
        y = 55 if "frontal" in lab else -75 if "occipital" in lab else rng.uniform(-60, 50)
        return np.array([s * rng.uniform(30, 50), y, rng.uniform(5, 50)]), np.array([13, 15, 12])
    if cat in ("thalamus", "basal_ganglia", "amygdala", "hippocampus"):
        return np.array([s * 14, -10 + rng.uniform(-8, 8), 2 + rng.uniform(-5, 5)]), np.array([7, 9, 7])
    if cat == "white_matter":
        return np.array([s * 18 + rng.uniform(-4, 4), rng.uniform(-10, 10), 12 + rng.uniform(-6, 6)]), np.array([20, 30, 18])
    return np.array([s * 5 + rng.uniform(-3, 3), -5 + rng.uniform(-9, 9), rng.uniform(-8, 8)]), np.array([6, 8, 6])


def main(out, flip_lr=False):
    out = Path(out)
    (out / "raw/bodyparts3d").mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "data/raw/bodyparts3d/metadata", out / "raw/bodyparts3d/metadata", dirs_exist_ok=True)
    (out / "raw/brainnetome/labels").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data/raw/brainnetome/labels/BN_Atlas_246_LUT.txt", out / "raw/brainnetome/labels/")
    cfg = load_config(overrides={"project": {"data_dir": str(out)}})
    bp, bn = BodyParts3DAdapter(cfg), BrainnetomeAdapter(cfg)
    for a in (bp, bn):
        a.discover(); a.build()
    dec = SelectionEngine(cfg, {"bodyparts3d": (bp.entities, bp.ontology), "brainnetome": (bn.entities, bn.ontology)}).run()
    rng = np.random.default_rng(1)
    objdir = out / "interim/bodyparts3d/obj_partof"
    objdir.mkdir(parents=True, exist_ok=True)
    sel = sorted([d for d in dec if d.source == "bodyparts3d" and d.decision in ("included", "reference")],
                 key=lambda d: (d.semantic_category, d.label))
    cnt, n = {}, 0
    verts = [d for d in sel if d.semantic_category == "vertebra"]
    verts.sort(key=lambda d: (({"C": 0, "T": 1, "L": 2, "S": 3}.get(spine_code(d.label)[:1], 9)), d.label))
    order = {d.entity_id: i for i, d in enumerate(verts)}
    for d in sel:
        i = order.get(d.entity_id, cnt.get(d.semantic_category, 0))
        cnt[d.semantic_category] = cnt.get(d.semantic_category, 0) + 1
        c, r = place(d, i, 0, rng)
        v, f = ellipsoid(c, r)
        # raw frame: centimetres, axes permuted (x_raw=Anterior, y_raw=Superior, z_raw=Right)
        raw = np.c_[v[:, 1], v[:, 2], v[:, 0]] / 10.0
        write_obj(objdir / (d.entity_id.split(":")[1] + ".obj"), raw, f)
        n += 1
    # Brainnetome volume: 2 mm MNI-like grid with LAS affine (standard)
    shape = (91, 109, 91)
    A = np.array([[-2, 0, 0, 90], [0, 2, 0, -126], [0, 0, 2, -72], [0, 0, 0, 1.0]])
    if flip_lr:
        A = np.array([[2, 0, 0, -90], [0, 2, 0, -126], [0, 0, 2, -72], [0, 0, 0, 1.0]])
    vol = np.zeros(shape, dtype=np.int16)
    ii, jj, kk = np.indices(shape)
    world = np.stack([ii, jj, kk, np.ones_like(ii)], -1) @ A.T
    k = 0
    for e in sorted(bn.entities.values(), key=lambda e: e.attributes["region_id"]):
        rid = e.attributes["region_id"]
        s = -1.0 if e.side == "L" else 1.0
        if flip_lr:                                  # labels contradict the affine (left at +x)
            s = -s
        if e.attributes["cortical"]:
            t = (k + 0.5) / 210.0; k += 1
            z = 1 - 2 * t; ph = k * 2.399963
            rr = np.sqrt(1 - z * z)
            c = np.array([abs(rr * np.cos(ph)) * 55 * s, rr * np.sin(ph) * 75 - 15, z * 50 + 10])
            rad = 8.0
        else:
            c = np.array([s * (12 + (rid % 5) * 3), -15 + (rid % 7) * 4, (rid % 3) * 4 - 2]); rad = 4.5
        m = ((world[..., 0] - c[0]) ** 2 + (world[..., 1] - c[1]) ** 2 + (world[..., 2] - c[2]) ** 2) < rad ** 2
        vol[m & (vol == 0)] = rid
    (out / "raw/brainnetome/atlas").mkdir(parents=True, exist_ok=True)
    save_nifti(out / "raw/brainnetome/atlas/BNA_MPM_thr25_1.25mm.nii.gz", vol, A)
    print(f"synthetic data: {n} BodyParts3D meshes, {len(np.unique(vol)) - 1} atlas regions -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], "--flip-lr" in sys.argv)

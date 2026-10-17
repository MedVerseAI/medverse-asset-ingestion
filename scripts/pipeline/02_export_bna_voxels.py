"""
02_export_bna_voxels.py       (plain Python:  python scripts/pipeline/02_export_bna_voxels.py)
-----------------------
STEP 2 of the pipeline: Human Brainnetome atlas  ->  one PLY mesh per region.

Reads   data/raw/brainnetome/atlas/BNA_MPM_thr25_1.25mm.nii.gz
        (a 3D grid of voxels; every voxel holds the id of the region it belongs to, 0 = background)
        data/raw/brainnetome/labels/BN_Atlas_246_LUT.txt   (id -> name + colour)

Writes  data/interim/brainnetome/voxel_export_pieces/<id:03d>_<name>.ply   (binary, closed surfaces, MNI mm)
        data/processed/reports/export_bna_voxels_report.txt

How a region becomes a mesh:
    1. mask      : voxels of that region = 1, everything else = 0
    2. crop      : cut a small box around the region (much faster than smoothing the whole head)
    3. pad       : add an empty border so the surface closes even if the region touches the box edge
    4. smooth    : light Gaussian blur so the surface is not made of visible cubes
    5. surface   : Marching Cubes at level 0.5 turns the blurred mask into triangles
    6. to MNI mm : voxel indices -> millimetres with the image affine
    7. winding   : if the affine mirrors space (det < 0) triangle order is reversed so normals point outwards
    8. write PLY : with the LUT colour on every vertex

Requirements:  pip install numpy scipy scikit-image nibabel
All paths come from medverse/paths.py.
"""
import os
import sys
import colorsys

import numpy as np
import nibabel as nib
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

# ---------------------------------------------------------------------------
# Make `import medverse` work without `pip install -e .`
# (also works inside Blender; if __file__ is undefined, set MEDVERSE_ROOT)
# ---------------------------------------------------------------------------
import sys as _sys
import os as _os
from pathlib import Path as _Path


def _bootstrap():
    cands = []
    if _os.environ.get("MEDVERSE_ROOT"):
        cands.append(_Path(_os.environ["MEDVERSE_ROOT"]) / "src")
    try:
        cands.append(_Path(__file__).resolve().parents[2] / "src")
    except NameError:
        pass
    for c in cands:
        if (c / "medverse").is_dir():
            if str(c) not in _sys.path:
                _sys.path.insert(0, str(c))
            return


_bootstrap()

# ---------------------------------------------------------------------------
# Import project modules
# ---------------------------------------------------------------------------
from medverse.anatomy.config import (
    BRAINNETOME_BASE_PATH,
    BN_NII_DIR,
    BN_LUT_PATH,
    BN_PIECES_DIR,
    EXPORT_BNA_REPORT_PATH,
    ensure_output_dirs,
)
from medverse.anatomy.classes import log, warn, reset_state

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
MPM_FILENAME = "BNA_MPM_thr25_1.25mm.nii.gz"   # maximum-probability-map atlas, 1.25 mm voxels
SMOOTH_SIGMA = 0.8      # Gaussian blur of each mask before meshing (0 = no smoothing, blocky look)
MIN_VOXELS = 10         # regions with fewer voxels are skipped
EXPECTED_REGIONS = 246  # Brainnetome has 246 regions (1-210 cortical, 211-246 subcortical)


def find_atlas():
    """Locate the atlas file: nii_gz_data first, then anywhere under the Brainnetome folder."""
    direct = os.path.join(BN_NII_DIR, MPM_FILENAME)
    if os.path.isfile(direct):
        return direct
    for dp, _, fns in os.walk(BRAINNETOME_BASE_PATH):
        if MPM_FILENAME in fns:
            return os.path.join(dp, MPM_FILENAME)
    raise FileNotFoundError(f"{MPM_FILENAME} not found in {BN_NII_DIR} or anywhere under {BRAINNETOME_BASE_PATH}")


def load_lut(path):
    """FreeSurfer LUT 'index name R G B A'  ->  {id: (name, (r, g, b))}.  Empty dict if missing."""
    lut = {}
    if not os.path.exists(path):
        warn(f"LUT not found: {path}; using generated names and colours")
        return lut
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 5 or line.lstrip().startswith("#"):
                continue
            try:
                idx = int(parts[0])
                r, g, b = (int(x) for x in parts[-4:-1])
            except ValueError:
                continue
            lut[idx] = (parts[1], (r, g, b))
    log(f"LUT: {len(lut)} entries read from {path}")
    return lut


def default_color(i):
    """Distinct pleasant colour for regions that have no LUT entry (golden-ratio hue spacing)."""
    r, g, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.65, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def safe_name(name):
    """Same rule as integration_geometry.safe_name, so file names match the LUT names exactly."""
    return "".join(c for c in name if c.isalnum() or c in "_-")


def write_ply_binary(path, verts, faces, rgb):
    """Binary little-endian triangle PLY with one colour for all vertices."""
    v = np.empty(len(verts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                    ("r", "u1"), ("g", "u1"), ("b", "u1")])
    v["x"], v["y"], v["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    v["r"], v["g"], v["b"] = rgb
    f = np.empty(len(faces), dtype=[("n", "u1"), ("idx", "<i4", (3,))])
    f["n"] = 3
    f["idx"] = faces
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(v)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        f"element face {len(f)}\n"
        "property list uchar int vertex_indices\nend_header\n"
    )
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.tobytes())
        fh.write(f.tobytes())


def crop_box(mask, margin):
    """(lo, hi) voxel corners of the region's bounding box grown by `margin`, clipped to the image."""
    idx = np.argwhere(mask)
    lo = np.maximum(idx.min(axis=0) - margin, 0)
    hi = np.minimum(idx.max(axis=0) + 1 + margin, mask.shape)
    return lo, hi


def region_to_mesh(mask, affine, flip):
    """Binary mask (whole image) -> (verts in MNI mm, faces).  Raises ValueError/RuntimeError if no surface."""
    margin = int(np.ceil(3 * SMOOTH_SIGMA)) + 1          # blur reaches ~3 sigma; keep the box clear of it
    lo, hi = crop_box(mask, margin)
    sub = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    vol = np.pad(sub.astype(np.float32), 1)               # empty border -> surface always closes
    if SMOOTH_SIGMA > 0:
        vol = gaussian_filter(vol, SMOOTH_SIGMA)
    verts, faces, _, _ = marching_cubes(vol, level=0.5)
    verts = verts - 1 + lo                                # undo padding, go back to full-image voxel coordinates
    verts = nib.affines.apply_affine(affine, verts)       # voxel indices -> MNI millimetres
    if flip:
        faces = faces[:, ::-1]
    return verts, faces


def main():
    reset_state()
    ensure_output_dirs()
    log.section("Brainnetome atlas -> PLY pieces")
    mpm_path = find_atlas()
    log(f"atlas  : {mpm_path}")
    log(f"LUT    : {BN_LUT_PATH}")
    log(f"output : {BN_PIECES_DIR}")

    img = nib.load(mpm_path)
    data = np.rint(np.asarray(img.dataobj)).astype(np.int32)
    affine = img.affine
    flip = bool(np.linalg.det(affine[:3, :3]) < 0)        # mirrored affine -> reverse triangle order
    ids = [int(i) for i in np.unique(data) if i > 0]
    log(f"volume shape: {data.shape} | regions found: {len(ids)} | affine mirrors space (det<0): {flip}")
    if len(ids) != EXPECTED_REGIONS:
        warn(f"expected {EXPECTED_REGIONS} regions, found {len(ids)}")

    lut = load_lut(BN_LUT_PATH)
    exported, skipped, cx = 0, [], {"L": [], "R": []}

    for rid in ids:
        mask = data == rid
        n = int(mask.sum())
        if n < MIN_VOXELS:
            skipped.append(rid)
            warn(f"region {rid}: only {n} voxels, skipped")
            continue
        try:
            verts, faces = region_to_mesh(mask, affine, flip)
        except (ValueError, RuntimeError) as exc:
            skipped.append(rid)
            warn(f"region {rid}: no surface ({exc}), skipped")
            continue

        name, color = lut.get(rid, (f"Region_{rid}", default_color(rid)))
        fname = f"{rid:03d}_{safe_name(name)}.ply"
        write_ply_binary(os.path.join(BN_PIECES_DIR, fname), verts, faces, color)
        exported += 1
        if name.endswith("_L"):
            cx["L"].append(verts[:, 0].mean())
        elif name.endswith("_R"):
            cx["R"].append(verts[:, 0].mean())
        log(f"{fname:48s} voxels {n:7d} | verts {len(verts):7d} | faces {len(faces):7d}")

    log.section("Summary")
    log(f"exported {exported} pieces to {BN_PIECES_DIR}")
    if skipped:
        log(f"skipped regions: {skipped}")
    if cx["L"] and cx["R"]:
        xl, xr = float(np.mean(cx["L"])), float(np.mean(cx["R"]))
        log(f"mean x of *_L regions = {xl:+.1f} mm, of *_R regions = {xr:+.1f} mm")
        if xl > xr:
            warn("left hemisphere lies at +x (LAS-like axes); the integration step will mirror x automatically")
    log.save(EXPORT_BNA_REPORT_PATH)
    return 0 if exported else 1


if __name__ == "__main__":
    sys.exit(main())
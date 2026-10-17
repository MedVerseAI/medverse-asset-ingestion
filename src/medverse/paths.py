"""
src/medverse/paths.py

Single source of truth for every filesystem location used by the pipeline.

Nothing outside this module should contain a machine-specific path.

Resolution order
----------------
Repository root:
    1. MEDVERSE_ROOT environment variable (needed when a script runs
       inside Blender's text editor, where __file__ may not exist).
    2. Walk up from this file until pyproject.toml or LICENSE is found.

Data directory:
    1. MEDVERSE_DATA_DIR environment variable (e.g. a large external drive).
    2. <root>/data.

Layout (see docs/data/download_and_layout.md)
---------------------------------------------
data/raw/        original downloads, never modified
data/interim/    extracted / intermediate files
data/processed/  final outputs (.blend model) and reports
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_ROOT = "MEDVERSE_ROOT"
ENV_DATA = "MEDVERSE_DATA_DIR"


def _find_root() -> Path:
    env = os.environ.get(ENV_ROOT)
    if env:
        root = Path(env).expanduser().resolve()
        if not root.is_dir():
            raise RuntimeError(
                f"{ENV_ROOT} points to a directory that does not exist: {root}"
            )
        return root

    markers = ("pyproject.toml", "LICENSE")

    for parent in Path(__file__).resolve().parents:
        if any((parent / marker).is_file() for marker in markers):
            return parent

    raise RuntimeError(
        f"Cannot locate the repository root. "
        f"Set the {ENV_ROOT} environment variable."
    )


# --------------------------------------------------------------------------
# Root and data directories
# --------------------------------------------------------------------------

ROOT: Path = _find_root()
DATA: Path = Path(
    os.environ.get(ENV_DATA, ROOT / "data")
).expanduser().resolve()

RAW: Path = DATA / "raw"
INTERIM: Path = DATA / "interim"
PROCESSED: Path = DATA / "processed"


# --------------------------------------------------------------------------
# BodyParts3D
# --------------------------------------------------------------------------

BP3D_RAW: Path = RAW / "bodyparts3d"
BP3D_METADATA: Path = BP3D_RAW / "metadata"
BP3D_ARCHIVES: Path = BP3D_RAW / "archives"
BP3D_CHECKSUMS: Path = BP3D_RAW / "checksums.sha256"
BP3D_README: Path = BP3D_RAW / "README_e.html"

BP3D_INTERIM: Path = INTERIM / "bodyparts3d"
BP3D_OBJ_ISA: Path = BP3D_INTERIM / "obj_isa"
BP3D_OBJ_PARTOF: Path = BP3D_INTERIM / "obj_partof"

# --- BodyParts3D export outputs (interim) ---
BP3D_EXPORT_DIR: Path = BP3D_INTERIM / "export_pieces"
BP3D_EXPORT_MESHES: Path = BP3D_EXPORT_DIR / "meshes"
BP3D_EXPORT_REFERENCE: Path = BP3D_EXPORT_DIR / "reference"
BP3D_EXPORT_MANIFEST: Path = BP3D_EXPORT_DIR / "manifest.json"

# Name of the folder created inside each extracted archive.
_BP3D_ARCHIVE_SUBDIR = {
    "isa": "isa_BP3D_4.0_obj_99",
    "partof": "partof_BP3D_4.0_obj_99",
}


# --------------------------------------------------------------------------
# Human Brainnetome
# --------------------------------------------------------------------------

# NOTE: lowercase on purpose, must match the folder name on disk exactly
# (paths are case-sensitive on Linux).
BN_RAW: Path = RAW / "brainnetome"
BN_ATLAS: Path = BN_RAW / "atlas"
BN_LABELS: Path = BN_RAW / "labels"
BN_LUT: Path = BN_LABELS / "BN_Atlas_246_LUT.txt"
BN_MPM: Path = BN_ATLAS / "BNA_MPM_thr25_1.25mm.nii.gz"

BN_INTERIM: Path = INTERIM / "brainnetome"
BN_PM_DIR: Path = BN_INTERIM / "pm_3d_246"            # per-region NIfTI volumes
BN_PIECES_DIR: Path = BN_INTERIM / "voxel_export_pieces"  # exported .ply voxels


# --------------------------------------------------------------------------
# Final outputs
# --------------------------------------------------------------------------

FINAL: Path = PROCESSED / "final"
FINAL_BLEND: Path = FINAL / "anatomical_model.blend"

REPORTS: Path = PROCESSED / "reports"
EXPORT_BP3D_REPORT: Path = REPORTS / "export_bodyparts3d_report.txt"
EXPORT_BNA_REPORT: Path = REPORTS / "export_bna_voxels_report.txt"
INTEGRATION_REPORT: Path = REPORTS / "integration_report.txt"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def bp3d_obj_dir(tree: str) -> Path:
    """Return the folder containing the FJxxxx.obj files of one tree.

    The ZIPs extract into a nested folder, so this returns the nested folder
    when it exists and the extraction root otherwise.
    """
    if tree not in _BP3D_ARCHIVE_SUBDIR:
        raise ValueError(f"tree must be 'isa' or 'partof', got {tree!r}")

    base = BP3D_OBJ_ISA if tree == "isa" else BP3D_OBJ_PARTOF
    nested = base / _BP3D_ARCHIVE_SUBDIR[tree]

    return nested if nested.is_dir() else base


def bp3d_metadata_file(name: str) -> Path:
    """Return the path of one BodyParts3D metadata table."""
    return BP3D_METADATA / name


def ensure_dirs(*paths: Path) -> None:
    """Create directories (and parents) if missing."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def ensure_output_dirs() -> None:
    """Create every output directory the pipeline writes to."""
    ensure_dirs(
        BP3D_EXPORT_MESHES,
        BP3D_EXPORT_REFERENCE,
        BN_PM_DIR,
        BN_PIECES_DIR,
        FINAL,
        REPORTS,
    )


def describe() -> dict[str, Path]:
    """Return all resolved locations for diagnostics."""
    return {
        key: value
        for key, value in globals().items()
        if key.isupper() and isinstance(value, Path)
    }

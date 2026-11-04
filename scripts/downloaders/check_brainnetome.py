"""
scripts/downloaders/check_brainnetome.py

Brainnetome is downloaded MANUALLY (see docs/data/download_and_layout.md, section 3).
This script only checks that the files are where the pipeline expects them,
and records their SHA-256 hashes.   Run:  python scripts/downloaders/check_brainnetome.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Support both common project layouts:
#   medverse-asset-ingestion/medverse/
#   medverse-asset-ingestion/src/medverse/
for package_root in (REPO_ROOT, REPO_ROOT / "src"):
    if (package_root / "medverse").is_dir():
        package_root_str = str(package_root)
        if package_root_str not in sys.path:
            sys.path.insert(0, package_root_str)

from medverse import paths
from medverse.download import verify_zip, write_checksums

# (file, folder, required?)  Only the LUT is confirmed: it is the one Brainnetome input
# read by the integration script. The rest are candidates until the input of
# export_bna_voxels.py is confirmed.
EXPECTED = [
    ("BN_Atlas_freesurfer.zip", paths.BN_ATLAS, False),
    ("BN_Atlas_246_LUT.txt", paths.BN_LABELS, True),
    ("BN_Atlas_246_1mm.nii.gz", paths.BN_ATLAS, False),
    ("BN_Atlas_246_2mm.nii.gz", paths.BN_ATLAS, False),
    ("BN_Atlas_246_3mm.nii.gz", paths.BN_ATLAS, False),
    ("BNA_MPM_thr25_1.25mm.nii.gz", paths.BN_ATLAS, False),
    ("BNA_PM_3D_246.zip", paths.BN_ATLAS, False),
    ("BNA_subregions.xlsx", paths.BN_LABELS, False),
]


def main() -> int:
    problems, present = [], []
    for name, folder, required in EXPECTED:
        f = folder / name
        tag = "ok"
        if f.is_file() and f.stat().st_size > 0:
            if f.suffix == ".zip":
                try:
                    verify_zip(f)
                except RuntimeError as exc:
                    tag = f"CORRUPT: {exc}"
                    if required:
                        problems.append(name)
            if tag == "ok":
                present.append(f)
        else:
            tag = "MISSING" if required else "missing (optional)"
            if required:
                problems.append(name)
        print(f"[{tag}] {f}")

    if present:
        out = paths.BN_RAW / "checksums.sha256"
        write_checksums(present, paths.BN_RAW, out)
        print(f"\nChecksums written to {out}")
    if problems:
        print(f"\nRequired files missing or corrupt: {problems}")
        return 1
    print("\nAll required Brainnetome files are in place.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

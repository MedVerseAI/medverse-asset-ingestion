"""
scripts/downloaders/bodyparts3d.py

Automated Downloader & Extractor for BodyParts3D dataset.

Data layout:
    data/
    ├── raw/bodyparts3d/
    │   ├── README_e.html
    │   ├── metadata/       # six metadata tables
    │   └── archives/       # original ZIP archives
    └── interim/bodyparts3d/
        ├── obj_isa/
        └── obj_partof/
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
from medverse.download import download, extract, verify_zip, write_checksums

BASE_URL = "https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST"

METADATA_FILES = [
    "isa_parts_list_e.txt",
    "partof_parts_list_e.txt",
    "partof_inclusion_relation_list.txt",
    "isa_inclusion_relation_list.txt",
    "isa_element_parts.txt",
    "partof_element_parts.txt",
]
ARCHIVES = {                      # archive file -> extraction folder
    "isa_BP3D_4.0_obj_99.zip": paths.BP3D_OBJ_ISA,
    "partof_BP3D_4.0_obj_99.zip": paths.BP3D_OBJ_PARTOF,
}


def main() -> None:
    print("MedVerse downloader: BodyParts3D v4.0\n" + "=" * 40)
    download(f"{BASE_URL}/README_e.html", paths.BP3D_README)
    for name in METADATA_FILES:
        download(f"{BASE_URL}/{name}", paths.BP3D_METADATA / name)
    for name in ARCHIVES:
        download(f"{BASE_URL}/{name}", paths.BP3D_ARCHIVES / name)

    # Verify every archive BEFORE extracting; stop on the first corrupt one.
    for name in ARCHIVES:
        verify_zip(paths.BP3D_ARCHIVES / name)
        print(f"[VERIFIED] {name}")

    raw_files = [paths.BP3D_README,
                 *(paths.BP3D_METADATA / n for n in METADATA_FILES),
                 *(paths.BP3D_ARCHIVES / n for n in ARCHIVES)]
    write_checksums(raw_files, paths.BP3D_RAW, paths.BP3D_CHECKSUMS)
    print(f"[OK] {paths.BP3D_CHECKSUMS}")

    for name, dest in ARCHIVES.items():
        extract(paths.BP3D_ARCHIVES / name, dest)

    print(f"\nDONE\nRaw:     {paths.BP3D_RAW}\nInterim: {paths.BP3D_INTERIM}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOPPED] cancelled.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)
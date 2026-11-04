"""
scripts/downloaders/bodyparts3d.py

Automated Downloader, Validator & Extractor for BodyParts3D dataset.

Data layout:
    data/
    ├── raw/bodyparts3d/
    │   ├── README_e.html
    │   ├── checksums.sha256
    │   ├── metadata/       # six metadata tables
    │   └── archives/       # original ZIP archives (preserved by default)
    └── interim/bodyparts3d/
        ├── obj_isa/
        └── obj_partof/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

for package_root in (REPO_ROOT, REPO_ROOT / "src"):
    if (package_root / "medverse").is_dir():
        package_root_str = str(package_root)
        if package_root_str not in sys.path:
            sys.path.insert(0, package_root_str)

from medverse import paths
from medverse.download import (
    download,
    extract,
    verify_checksums,
    verify_zip,
    write_checksums,
)

BASE_URL = "https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST"

METADATA_FILES = [
    "isa_parts_list_e.txt",
    "partof_parts_list_e.txt",
    "partof_inclusion_relation_list.txt",
    "isa_inclusion_relation_list.txt",
    "isa_element_parts.txt",
    "partof_element_parts.txt",
]

ARCHIVES = {  # archive file -> (extraction folder, tree key)
    "isa_BP3D_4.0_obj_99.zip": (paths.BP3D_OBJ_ISA, "isa"),
    "partof_BP3D_4.0_obj_99.zip": (paths.BP3D_OBJ_PARTOF, "partof"),
}


def _is_extracted(tree: str) -> bool:
    """Return True if the target interim directory already contains extracted .obj files."""
    obj_dir = paths.bp3d_obj_dir(tree)
    return obj_dir.is_dir() and any(obj_dir.glob("*.obj"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download, validate, and extract the BodyParts3D v4.0 dataset."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing raw files and checksums without downloading or extracting.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download all files even if they already exist locally.",
    )
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="Re-extract ZIP archives even if .obj files already exist in data/interim/.",
    )
    parser.add_argument(
        "--delete-archives",
        action="store_true",
        help="Delete raw ZIP archives after extraction (default: keep raw archives).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("MedVerse downloader: BodyParts3D v4.0\n" + "=" * 40)

    paths.ensure_dirs(
        paths.BP3D_RAW,
        paths.BP3D_METADATA,
        paths.BP3D_ARCHIVES,
        paths.BP3D_OBJ_ISA,
        paths.BP3D_OBJ_PARTOF,
    )

    if args.verify_only:
        if paths.BP3D_CHECKSUMS.is_file():
            problems = verify_checksums(paths.BP3D_CHECKSUMS, paths.BP3D_RAW)
            if problems:
                raise RuntimeError(f"Checksum verification failed: {problems}")
            print(f"[VERIFIED] All files match {paths.BP3D_CHECKSUMS}")
        for name in ARCHIVES:
            archive_path = paths.BP3D_ARCHIVES / name
            verify_zip(archive_path)
            print(f"[VERIFIED] {name}")
        return

    # 1. Pre-check existing checksum manifest if present
    if paths.BP3D_CHECKSUMS.is_file() and not args.force_download:
        problems = verify_checksums(paths.BP3D_CHECKSUMS, paths.BP3D_RAW)
        if problems:
            print(f"[WARN] Existing files failed checksum check ({problems}). Re-fetching affected files...")
            for item in problems:
                rel_path = item.split(": ", 1)[1]
                (paths.BP3D_RAW / Path(rel_path)).unlink(missing_ok=True)

    # 2. Download README, metadata tables, and ZIP archives
    download(f"{BASE_URL}/README_e.html", paths.BP3D_README, force=args.force_download)
    for name in METADATA_FILES:
        download(f"{BASE_URL}/{name}", paths.BP3D_METADATA / name, force=args.force_download)
    for name in ARCHIVES:
        download(f"{BASE_URL}/{name}", paths.BP3D_ARCHIVES / name, force=args.force_download)

    # 3. Verify every archive BEFORE extracting; auto-redownload once if corrupt
    for name in ARCHIVES:
        archive_path = paths.BP3D_ARCHIVES / name
        try:
            verify_zip(archive_path)
            print(f"[VERIFIED] {name}")
        except RuntimeError as exc:
            print(f"[WARN] {exc}. Re-downloading {name}...")
            download(f"{BASE_URL}/{name}", archive_path, force=True)
            verify_zip(archive_path)
            print(f"[VERIFIED] {name}")

    # 4. Write SHA-256 checksums manifest for all raw files
    raw_files = [
        paths.BP3D_README,
        *(paths.BP3D_METADATA / n for n in METADATA_FILES),
        *(paths.BP3D_ARCHIVES / n for n in ARCHIVES),
    ]
    write_checksums(raw_files, paths.BP3D_RAW, paths.BP3D_CHECKSUMS)
    print(f"[OK] {paths.BP3D_CHECKSUMS}")

    # 5. Extract archives into data/interim/bodyparts3d/ (skip if already extracted)
    for name, (dest, tree) in ARCHIVES.items():
        if _is_extracted(tree) and not args.force_extract:
            print(f"[SKIP EXTRACT] {name} (.obj files already present in {paths.bp3d_obj_dir(tree)})")
            continue
        if not extract(paths.BP3D_ARCHIVES / name, dest, delete_archive=args.delete_archives):
            raise RuntimeError(f"Extraction failed for {name}")

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
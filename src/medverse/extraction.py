"""
src/medverse/extraction.py
Cross-platform archive extraction with progress tracking.
"""
from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def extract(archive: Path | str, destination: Path | str, delete_archive: bool = False) -> bool:
    """
    Extract a .zip or .tar.gz archive with a progress bar.
    Preserves the raw archive by default (delete_archive=False).
    """
    archive_path = Path(archive)
    dest_path = Path(destination)

    if not archive_path.is_file():
        print(f"[EXTRACT] Error: Archive not found at {archive_path}")
        return False

    dest_path.mkdir(parents=True, exist_ok=True)
    print(f"[EXTRACT] {archive_path.name} -> {dest_path}")

    try:
        name_lower = archive_path.name.lower()
        if name_lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = zf.infolist()
                total = len(members)
                if not total:
                    print(f"[OK] {dest_path} (empty archive)")
                    return True
                for i, member in enumerate(members, 1):
                    zf.extract(member, dest_path)
                    filled = int(30 * i / total)
                    print(
                        f"\r[{'=' * filled}{'-' * (30 - filled)}] "
                        f"{i * 100 / total:6.2f}% {i}/{total} files",
                        end="",
                        flush=True,
                    )
            print(f"\n[OK] {dest_path}")

        elif name_lower.endswith((".tar.gz", ".tgz", ".tar")):
            with tarfile.open(archive_path, "r:*") as tf:
                tf.extractall(dest_path)
            print(f"[OK] {dest_path}")

        else:
            print(f"[EXTRACT] Unsupported archive format: {archive_path.name}")
            return False

        if delete_archive:
            archive_path.unlink(missing_ok=True)
            print(f"[CLEANUP] Removed raw archive: {archive_path.name}")

        return True

    except (zipfile.BadZipFile, tarfile.ReadError, RuntimeError, OSError) as exc:
        print(f"\n[EXTRACT] FATAL ERROR: Archive is corrupted or incomplete: {exc}")
        return False


# Alias for backward compatibility with unit tests
extract_dataset = extract
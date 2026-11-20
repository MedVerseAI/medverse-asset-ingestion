"""
src/medverse/download.py
Download, verify and extract helpers shared by the dataset downloaders.
"""
from __future__ import annotations

from pathlib import Path
import requests

from medverse.extraction import extract, extract_dataset
from medverse.validation import (
    sha256_of,
    verify_checksums,
    verify_file,
    verify_zip,
    write_checksums,
)

CHUNK_SIZE_5MB = 5 * 1024 * 1024


def download(url: str, destination: Path | str, force: bool = False) -> bool:
    """
    Stream-download ``url`` to ``destination`` unless a non-empty file already exists.
    Writes to a temporary ``.part`` file first so interrupted downloads never leave
    corrupt partial files in ``data/raw/``.
    """
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.is_file() and dest.stat().st_size > 0 and not force:
        print(f"[SKIP] {dest.name} (already exists)")
        return False

    temp_dest = dest.with_suffix(dest.suffix + ".part")
    print(f"[DOWNLOAD] {dest.name}")

    try:
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(temp_dest, "wb") as fh:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE_5MB):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        filled = int(30 * min(downloaded, total_size) / total_size)
                        bar = "=" * filled + "-" * (30 - filled)
                        print(
                            f"\r[{bar}] {downloaded * 100 / total_size:6.2f}% "
                            f"{downloaded / 1048576:.1f}/{total_size / 1048576:.1f} MB",
                            end="",
                            flush=True,
                        )
                    else:
                        print(
                            f"\rDownloaded: {downloaded / 1048576:.1f} MB",
                            end="",
                            flush=True,
                        )

        temp_dest.replace(dest)
        print(f"\n[OK] {dest}")
        return True

    except Exception as exc:
        temp_dest.unlink(missing_ok=True)
        print(f"\n[ERROR] Failed to download {dest.name}: {exc}")
        raise


# Alias for backward compatibility
download_dataset = download

__all__ = [
    "download",
    "download_dataset",
    "extract",
    "extract_dataset",
    "sha256_of",
    "verify_checksums",
    "verify_file",
    "verify_zip",
    "write_checksums",
]
"""
src/medverse/download.py
Download, verify and extract helpers shared by the dataset downloaders.
"""
from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path


def _progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    downloaded = block_num * block_size
    if total_size > 0:
        downloaded = min(downloaded, total_size)
        filled = int(30 * downloaded / total_size)
        bar = "=" * filled + "-" * (30 - filled)
        print(f"\r[{bar}] {downloaded * 100 / total_size:6.2f}% "
              f"{downloaded / 1048576:.1f}/{total_size / 1048576:.1f} MB", end="", flush=True)
    else:
        print(f"\rDownloaded: {downloaded / 1048576:.1f} MB", end="", flush=True)


def download(url: str, destination: Path) -> bool:
    """Download ``url`` unless ``destination`` exists. Returns True if downloaded."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(f"[SKIP] {destination.name}")
        return False
    print(f"[DOWNLOAD] {destination.name}")
    try:
        urllib.request.urlretrieve(url, destination, reporthook=_progress_hook)
    except Exception:
        destination.unlink(missing_ok=True)      # never leave a partial file behind
        raise
    print(f"\n[OK] {destination}")
    return True


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def write_checksums(files: list[Path], base: Path, out: Path) -> None:
    """Write ``<sha256>  <path relative to base>`` lines (sha256sum format)."""
    lines = [f"{sha256_of(f)}  {f.relative_to(base).as_posix()}" for f in sorted(files)]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_checksums(checksum_file: Path, base: Path) -> list[str]:
    """Return a list of problems (empty list = all files match)."""
    problems = []
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        f = base / rel
        if not f.is_file():
            problems.append(f"missing: {rel}")
        elif sha256_of(f) != digest:
            problems.append(f"hash mismatch: {rel}")
    return problems


def verify_zip(archive: Path) -> None:
    """Raise if the ZIP cannot be opened or contains a corrupt entry."""
    try:
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{archive.name} is not a valid ZIP: {exc}") from exc
    if bad is not None:
        raise RuntimeError(f"{archive.name}: corrupt entry '{bad}'")


def extract(archive: Path, destination: Path) -> None:
    """Extract a ZIP archive with a progress bar."""
    destination.mkdir(parents=True, exist_ok=True)
    print(f"[EXTRACT] {archive.name}")
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        total = len(members)
        if not total:
            print(f"[OK] {destination} (empty archive)")
            return
        for i, member in enumerate(members, 1):
            zf.extract(member, destination)
            filled = int(30 * i / total)
            print(f"\r[{'=' * filled}{'-' * (30 - filled)}] {i * 100 / total:6.2f}% {i}/{total} files",
                  end="", flush=True)
    print(f"\n[OK] {destination}")
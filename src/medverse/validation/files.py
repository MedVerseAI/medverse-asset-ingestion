"""
src/medverse/validation/files.py
Cross-platform SHA-256 checksum and archive integrity validation.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

CHUNK_SIZE_64KB = 65536


def sha256_of(path: Path | str, chunk: int = CHUNK_SIZE_64KB) -> str:
    """Calculate the SHA-256 hex digest of a file in 64KB chunks."""
    file_path = Path(path)
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_file(file_path: Path | str, expected_hash: str | None = None) -> bool:
    """Verify that a file exists, is non-empty, and matches ``expected_hash`` if provided."""
    path = Path(file_path)
    if not path.is_file() or path.stat().st_size == 0:
        print(f"[Validation] File missing or empty: {path}")
        return False

    if expected_hash is None:
        return True

    print(f"[Validation] Validating SHA-256 checksum for {path.name}...")
    calculated = sha256_of(path)
    if calculated.lower() == expected_hash.lower():
        print(f"[Validation] SUCCESS: {path.name} is intact.")
        return True

    print(f"[Validation] ERROR: Hash mismatch for {path.name}!")
    print(f"  Expected: {expected_hash}")
    print(f"  Actual:   {calculated}")
    return False


def verify_zip(archive: Path | str) -> None:
    """Raise RuntimeError if the ZIP cannot be opened or contains a corrupt entry."""
    archive_path = Path(archive)
    if not archive_path.is_file():
        raise RuntimeError(f"{archive_path.name} is missing: {archive_path}")
    try:
        with zipfile.ZipFile(archive_path) as zf:
            bad = zf.testzip()
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{archive_path.name} is not a valid ZIP: {exc}") from exc
    if bad is not None:
        raise RuntimeError(f"{archive_path.name}: corrupt entry '{bad}'")


def write_checksums(files: list[Path], base: Path, out: Path) -> None:
    """Write ``<sha256>  <path relative to base>`` lines (sha256sum format)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{sha256_of(f)}  {f.relative_to(base).as_posix()}"
        for f in sorted(files)
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_checksums(checksum_file: Path, base: Path) -> list[str]:
    """Return a list of problems (empty list = all files match)."""
    problems: list[str] = []
    if not checksum_file.is_file():
        return [f"missing checksum file: {checksum_file.name}"]

    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        f = base / Path(rel)
        if not f.is_file():
            problems.append(f"missing: {rel}")
        elif sha256_of(f) != digest.strip():
            problems.append(f"hash mismatch: {rel}")
    return problems

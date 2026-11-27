"""Unit tests for dataset downloading, Zip/Tar Slip extraction guards, and strict validation."""
from __future__ import annotations

import importlib.util
import io
import os
import tarfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest

import conftest  # noqa: F401
from medverse import paths
from medverse.download import download
from medverse.extraction import extract
from medverse.validation import (
    sha256_of,
    verify_checksums,
    verify_file,
    verify_zip,
    write_checksums,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_bp3d_downloader():
    spec = importlib.util.spec_from_file_location(
        "bp3d_downloader", REPO_ROOT / "scripts" / "downloaders" / "bodyparts3d.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_paths_resolution():
    assert paths.ROOT.is_dir()
    assert paths.BP3D_RAW == paths.RAW / "bodyparts3d"


def test_validation_missing_file_and_hash(tmp_path):
    assert not verify_file(tmp_path / "nonexistent.zip")
    valid_zip = tmp_path / "valid.zip"
    with zipfile.ZipFile(valid_zip, "w") as zf:
        zf.writestr("dummy.txt", "MedVerse VR Data")
    assert verify_file(valid_zip, sha256_of(valid_zip))
    assert not verify_file(valid_zip, "0" * 64)


def test_verify_zip_and_checksums_manifest(tmp_path):
    invalid_zip = tmp_path / "invalid.zip"
    invalid_zip.write_bytes(os.urandom(512))
    valid_zip = tmp_path / "valid.zip"
    dummy_txt = tmp_path / "dummy.txt"
    dummy_txt.write_text("MedVerse VR Data", encoding="utf-8")
    with zipfile.ZipFile(valid_zip, "w") as zf:
        zf.write(dummy_txt, arcname="dummy.txt")

    verify_zip(valid_zip)
    with pytest.raises(RuntimeError):
        verify_zip(invalid_zip)

    cs_file = tmp_path / "checksums.sha256"
    write_checksums([valid_zip, dummy_txt], tmp_path, cs_file)
    assert verify_checksums(cs_file, tmp_path) == []


def test_extraction_preserves_raw_archive_by_default(tmp_path):
    invalid_zip = tmp_path / "bad.zip"
    invalid_zip.write_bytes(b"not-a-zip")
    valid_zip = tmp_path / "good.zip"
    with zipfile.ZipFile(valid_zip, "w") as zf:
        zf.writestr("dummy.txt", "MedVerse VR Data")

    out_dir = tmp_path / "extracted"
    assert not extract(invalid_zip, out_dir)
    assert extract(valid_zip, out_dir)
    assert (out_dir / "dummy.txt").is_file()
    assert valid_zip.is_file()


def test_extraction_blocks_zip_slip(tmp_path):
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../escaped.txt", "pwned")
    out_dir = tmp_path / "out"
    assert not extract(evil_zip, out_dir)
    assert not (tmp_path / "escaped.txt").exists()


def test_extraction_blocks_tar_slip(tmp_path):
    evil_tar = tmp_path / "evil.tar.gz"
    with tarfile.open(evil_tar, "w:gz") as tf:
        info = tarfile.TarInfo(name="../escaped_tar.txt")
        data = b"pwned"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    out_dir = tmp_path / "out"
    assert not extract(evil_tar, out_dir)
    assert not (tmp_path / "escaped_tar.txt").exists()


def test_download_atomic_streaming_skip_and_part_cleanup(tmp_path):
    dest = tmp_path / "sample.bin"
    payload = b"hello-medverse-streaming-payload"

    class _FakeResp:
        def __init__(self, chunks, fail=False):
            self.headers = {"content-length": str(sum(len(c) for c in chunks))}
            self._chunks = chunks
            self._fail = fail

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=1024):
            for c in self._chunks:
                yield c
                if self._fail:
                    raise ConnectionError("simulated network drop")

    with mock.patch("medverse.download.requests.get", return_value=_FakeResp([payload[:10], payload[10:]])):
        assert download("https://example.invalid/sample.bin", dest) is True
    assert dest.read_bytes() == payload
    assert not dest.with_suffix(".bin.part").exists()

    # Second call without force skips
    with mock.patch("medverse.download.requests.get") as mget:
        assert download("https://example.invalid/sample.bin", dest, force=False) is False
        mget.assert_not_called()

    # Failure cleans up partial .part file cleanly
    dest2 = tmp_path / "broken.bin"
    with mock.patch("medverse.download.requests.get", return_value=_FakeResp([b"partial"], fail=True)):
        with pytest.raises(ConnectionError):
            download("https://example.invalid/broken.bin", dest2)
    assert not dest2.exists()
    assert not dest2.with_suffix(".bin.part").exists()


def test_bodyparts3d_verify_only_fails_when_checksums_or_metadata_missing(tmp_path, monkeypatch):
    bp3d = _load_bp3d_downloader()
    raw = tmp_path / "raw" / "bodyparts3d"
    meta = raw / "metadata"
    arch = raw / "archives"
    meta.mkdir(parents=True)
    arch.mkdir(parents=True)

    monkeypatch.setattr(bp3d.paths, "BP3D_RAW", raw)
    monkeypatch.setattr(bp3d.paths, "BP3D_METADATA", meta)
    monkeypatch.setattr(bp3d.paths, "BP3D_ARCHIVES", arch)
    monkeypatch.setattr(bp3d.paths, "BP3D_README", raw / "README_e.html")
    monkeypatch.setattr(bp3d.paths, "BP3D_CHECKSUMS", raw / "checksums.sha256")

    # Even if valid ZIPs exist, missing checksums.sha256 and metadata must fail loudly
    for name in bp3d.ARCHIVES:
        with zipfile.ZipFile(arch / name, "w") as zf:
            zf.writestr("FJ1.obj", "v 0 0 0\n")

    with pytest.raises(RuntimeError, match="Missing required checksum manifest"):
        bp3d.verify_existing_dataset()

    # Writing checksums for only archives while metadata/README are missing must still fail
    write_checksums([arch / n for n in bp3d.ARCHIVES], raw, raw / "checksums.sha256")
    with pytest.raises(RuntimeError, match="Missing or empty required raw BodyParts3D files"):
        bp3d.verify_existing_dataset()

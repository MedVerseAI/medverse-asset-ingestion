import os
import shutil
import sys
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for package_root in (REPO_ROOT, REPO_ROOT / "src"):
    if (package_root / "medverse").is_dir():
        sys.path.insert(0, str(package_root))

from medverse import paths
from medverse.extraction import extract
from medverse.validation import (
    sha256_of,
    verify_checksums,
    verify_file,
    verify_zip,
    write_checksums,
)


class TestDatasetPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = REPO_ROOT / "tests" / "tmp_test_artifacts"
        cls.extract_dir = cls.test_dir / "extracted"
        cls.invalid_zip = cls.test_dir / "invalid_test.zip"
        cls.valid_zip = cls.test_dir / "valid_test.zip"
        cls.dummy_txt = cls.test_dir / "dummy.txt"
        cls.checksum_file = cls.test_dir / "checksums.sha256"

        cls.extract_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create an invalid zip (random bytes)
        cls.invalid_zip.write_bytes(os.urandom(1024))

        # 2. Create a valid zip archive
        cls.dummy_txt.write_text("MedVerse VR Data", encoding="utf-8")
        with zipfile.ZipFile(cls.valid_zip, "w") as zipf:
            zipf.write(cls.dummy_txt, arcname="dummy.txt")

        cls.valid_hash = sha256_of(cls.valid_zip)

    def test_paths_resolution(self):
        """Ensure centralized paths resolve across OS platforms."""
        self.assertTrue(paths.ROOT.is_dir())
        self.assertEqual(paths.BP3D_RAW, paths.RAW / "bodyparts3d")

    def test_validation_missing_file(self):
        self.assertFalse(verify_file( self.test_dir / "nonexistent.zip"))

    def test_validation_correct_hash(self):
        self.assertTrue(verify_file(self.valid_zip, self.valid_hash))

    def test_verify_zip_and_checksums_manifest(self):
        """Test verify_zip, write_checksums, and verify_checksums from docs/data_dictionary."""
        verify_zip(self.valid_zip)
        with self.assertRaises(RuntimeError):
            verify_zip(self.invalid_zip)

        write_checksums([self.valid_zip, self.dummy_txt], self.test_dir, self.checksum_file)
        problems = verify_checksums(self.checksum_file, self.test_dir)
        self.assertEqual(problems, [])

    def test_extraction_preserves_raw_archive_by_default(self):
        """Ensure extraction succeeds and keeps raw archive in place by default."""
        self.assertFalse(extract(self.invalid_zip, self.extract_dir))
        self.assertTrue(extract(self.valid_zip, self.extract_dir))
        self.assertTrue((self.extract_dir / "dummy.txt").is_file())
        self.assertTrue(self.valid_zip.is_file())  # Raw archive preserved

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.is_dir():
            shutil.rmtree(cls.test_dir)


if __name__ == "__main__":
    unittest.main()
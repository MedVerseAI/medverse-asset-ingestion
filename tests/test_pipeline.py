import os
import unittest
import hashlib
import zipfile
import shutil
from src.medverse.validation import verify_file
from src.medverse.extraction import extract_dataset

class TestDatasetPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Creates both valid and invalid dummy files for comprehensive testing."""
        cls.invalid_zip = "tests/invalid_test.zip"
        cls.valid_zip = "tests/valid_test.zip"
        cls.extract_dir = "tests/output/"
        cls.dummy_txt = "tests/dummy.txt"
        os.makedirs(cls.extract_dir, exist_ok=True)
        
        # 1. Create an invalid zip (just random bytes)
        with open(cls.invalid_zip, "wb") as f:
            f.write(os.urandom(1024))

        # 2. Create a real, structurally valid zip file
        with open(cls.dummy_txt, "w") as f:
            f.write("MedVerse VR Data")
        with zipfile.ZipFile(cls.valid_zip, 'w') as zipf:
            zipf.write(cls.dummy_txt, arcname="dummy.txt")

        # 3. Calculate the exact SHA-256 hash of the valid zip
        sha256 = hashlib.sha256()
        with open(cls.valid_zip, "rb") as f:
            sha256.update(f.read())
        cls.valid_hash = sha256.hexdigest()

    def test_validation_missing_file(self):
        self.assertFalse(verify_file("nonexistent_file.zip"))

    def test_validation_without_hash(self):
        self.assertTrue(verify_file(self.valid_zip))

    def test_validation_correct_hash(self):
        """Ensures the inspector passes a file with the mathematically correct hash."""
        self.assertTrue(verify_file(self.valid_zip, self.valid_hash))

    def test_extraction_invalid_file(self):
        """Ensures the unpacker gracefully fails on corrupted data."""
        self.assertFalse(extract_dataset(self.invalid_zip, self.extract_dir))

    def test_extraction_valid_file(self):
        """Ensures the unpacker successfully extracts a structurally sound zip."""
        result = extract_dataset(self.valid_zip, self.extract_dir)
        self.assertTrue(result)
        # Verify the file actually made it out of the zip and onto the hard drive
        self.assertTrue(os.path.exists(os.path.join(self.extract_dir, "dummy.txt")))

    @classmethod
    def tearDownClass(cls):
        """Cleans up all generated testing artifacts."""
        for file in [cls.invalid_zip, cls.valid_zip, cls.dummy_txt]:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists(cls.extract_dir):
            shutil.rmtree(cls.extract_dir)

if __name__ == "__main__":
    unittest.main()
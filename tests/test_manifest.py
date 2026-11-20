"""

Unit tests for anatomical label loading, manifest generation, and CLI execution.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for package_root in (REPO_ROOT, REPO_ROOT / "src"):
    if (package_root / "medverse").is_dir() and str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from medverse.manifest import build_manifest, load_anatomical_labels
from medverse.validation import sha256_of


class TestManifest(unittest.TestCase):
    def test_manifest_generation_lookup_fallback_and_sha256(self):
        """Verify label lookup, unmapped fallback, and SHA-256 output with mock files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            metadata_dir = tmp_path / "metadata"
            mesh_dir = tmp_path / "meshes"
            bp3d_dir = mesh_dir / "bodyparts3d"
            metadata_dir.mkdir(parents=True)
            bp3d_dir.mkdir(parents=True)

            # 3-line mock metadata table
            (metadata_dir / "isa_parts_list_e.txt").write_text(
                "concept id\trepresentation id\ten\n"
                "FJ1001\tBP1001\tHeart\n"
                "FJ1002\tBP1002\tBrain\n",
                encoding="utf-8",
            )

            # Two mock .glb files: one mapped, one unmapped
            heart_glb = bp3d_dir / "FJ1001.glb"
            unmapped_glb = bp3d_dir / "UNMAPPED_999.glb"
            heart_glb.write_bytes(b"mock-heart-glb-data")
            unmapped_glb.write_bytes(b"mock-unmapped-glb-data")

            labels = load_anatomical_labels(
                bp3d_metadata_dir=metadata_dir,
                bn_lut_path=tmp_path / "missing_lut.txt",
            )
            out_file = tmp_path / "manifest.json"
            manifest = build_manifest(mesh_dir=mesh_dir, out_file=out_file, labels=labels)

            self.assertTrue(out_file.is_file())
            written = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(manifest, written)
            self.assertEqual(manifest["schema_version"], "1.0.0")
            self.assertEqual(manifest["total_assets"], 2)

            by_id = {item["id"]: item for item in manifest["assets"]}
            self.assertEqual(by_id["FJ1001"]["name"], "Heart")
            self.assertEqual(by_id["FJ1001"]["format"], "glb")
            self.assertEqual(by_id["FJ1001"]["relative_path"], "bodyparts3d/FJ1001.glb")
            self.assertEqual(by_id["FJ1001"]["size_bytes"], heart_glb.stat().st_size)
            self.assertEqual(by_id["FJ1001"]["sha256"], sha256_of(heart_glb))

            # Unmapped files must not crash and should fall back to file stem
            self.assertEqual(by_id["UNMAPPED_999"]["name"], "UNMAPPED_999")
            self.assertEqual(by_id["UNMAPPED_999"]["sha256"], sha256_of(unmapped_glb))

    def test_element_specificity_and_brainnetome_lut(self):
        """Verify element_parts picks the most specific concept and BN LUT parses."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            metadata_dir = tmp_path / "metadata"
            metadata_dir.mkdir(parents=True)

            (metadata_dir / "isa_element_parts.txt").write_text(
                "concept id\tname\telement file id\n"
                "FMA1\tWhole Body\tFJ3413\n"
                "FMA1\tWhole Body\tFJ9999\n"
                "FMA2\tascending aorta\tFJ3413\n",
                encoding="utf-8",
            )

            bn_lut = tmp_path / "BN_Atlas_246_LUT.txt"
            bn_lut.write_text(
                "# Brainnetome Atlas LUT\n"
                "1\tSFG_L_7_1\t200\t100\t50\t0\n",
                encoding="utf-8",
            )

            labels = load_anatomical_labels(
                bp3d_metadata_dir=metadata_dir,
                bn_lut_path=bn_lut,
            )
            self.assertEqual(labels["FJ3413"], "ascending aorta")
            self.assertEqual(labels["1"], "SFG_L_7_1")
            self.assertEqual(labels["BNA_1"], "SFG_L_7_1")

    def test_cli_script_runs_cleanly(self):
        """Verify scripts/pipeline/04_generate_manifest.py runs end-to-end."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mesh_dir = tmp_path / "meshes"
            mesh_dir.mkdir()
            (mesh_dir / "sample.obj").write_text("v 0 0 0\n", encoding="utf-8")
            out_file = tmp_path / "out" / "manifest.json"

            cli_path = REPO_ROOT / "scripts" / "pipeline" / "04_generate_manifest.py"
            result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--input-dir",
                    str(mesh_dir),
                    "--output",
                    str(out_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue(out_file.is_file())


if __name__ == "__main__":
    unittest.main()
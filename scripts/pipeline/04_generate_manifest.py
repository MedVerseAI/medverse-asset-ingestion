"""

Generate manifest.json for exported 3D mesh assets.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for package_root in (REPO_ROOT, REPO_ROOT / "src"):
    if (package_root / "medverse").is_dir() and str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from medverse import paths
from medverse.manifest import build_manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index exported 3D meshes and write manifest.json."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=paths.INTERIM,
        help=f"Directory containing exported 3D meshes (default: {paths.INTERIM})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=paths.INTERIM / "manifest.json",
        help=f"Output manifest JSON path (default: {paths.INTERIM / 'manifest.json'})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = build_manifest(mesh_dir=args.input_dir, out_file=args.output)
    print(
        f"[Manifest] Indexed {manifest['total_assets']} asset(s) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
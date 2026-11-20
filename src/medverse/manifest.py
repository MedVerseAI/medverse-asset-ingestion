"""

Catalog exported 3D mesh assets with English anatomical labels, file sizes,
and SHA-256 checksums into a deterministic manifest.json file.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from medverse import paths
from medverse.validation import sha256_of

SUPPORTED_EXTENSIONS = {".glb", ".gltf", ".fbx", ".obj"}
SCHEMA_VERSION = "1.0.0"


def _parse_bp3d_parts_list(file_path: Path, labels: dict[str, str]) -> None:
    """Read a BodyParts3D *_parts_list_e.txt table into ``labels``."""
    if not file_path.is_file():
        return

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        cols = [c.strip() for c in line.split("\t")]
        if cols[0].lower() in {"concept id", "concept_id", "id"}:
            continue

        if len(cols) >= 3:
            concept_id, rep_id, name = cols[0], cols[1], cols[2]
            if name:
                if concept_id:
                    labels.setdefault(concept_id, name)
                if rep_id:
                    labels.setdefault(rep_id, name)
        elif len(cols) == 2:
            item_id, name = cols[0], cols[1]
            if item_id and name:
                labels.setdefault(item_id, name)


def _parse_bp3d_element_parts(file_path: Path, labels: dict[str, str]) -> None:
    """Map FJxxxx element IDs to their most specific BodyParts3D concept name."""
    if not file_path.is_file():
        return

    concept_counts: Counter[str] = Counter()
    candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        cols = [c.strip() for c in line.split("\t")]
        if len(cols) < 3 or cols[0].lower() in {"concept id", "concept_id", "id"}:
            continue

        concept_id, name, element_id = cols[0], cols[1], cols[2]
        if concept_id and name and element_id:
            concept_counts[concept_id] += 1
            candidates[element_id].append((concept_id, name))

    for element_id, choices in candidates.items():
        # Pick the concept with the fewest total elements (most specific organ).
        _, best_name = min(choices, key=lambda pair: concept_counts[pair[0]])
        labels.setdefault(element_id, best_name)


def _parse_bn_lut(file_path: Path, labels: dict[str, str]) -> None:
    """Read Brainnetome BN_Atlas_246_LUT.txt region IDs and names."""
    if not file_path.is_file():
        return

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        region_id, name = parts[0].strip(), parts[1].strip()
        if not region_id or not name:
            continue

        labels.setdefault(region_id, name)
        if region_id.isdigit():
            labels.setdefault(f"BNA_{region_id}", name)
            labels.setdefault(f"BNA_{int(region_id):03d}", name)


def load_anatomical_labels(
    bp3d_metadata_dir: Path | str | None = None,
    bn_lut_path: Path | str | None = None,
) -> dict[str, str]:
    """Load ID -> English anatomical name mappings from BodyParts3D and Brainnetome."""
    labels: dict[str, str] = {}

    bp3d_dir = Path(bp3d_metadata_dir) if bp3d_metadata_dir is not None else paths.BP3D_METADATA
    bn_lut = Path(bn_lut_path) if bn_lut_path is not None else paths.BN_LUT

    # Element tables map FJxxxx mesh IDs directly to the most specific organ name.
    for filename in ("isa_element_parts.txt", "partof_element_parts.txt"):
        _parse_bp3d_element_parts(bp3d_dir / filename, labels)

    # Parts lists map FMAxxxx / BPxxxx IDs (and any simple mock tables).
    for filename in ("isa_parts_list_e.txt", "partof_parts_list_e.txt"):
        _parse_bp3d_parts_list(bp3d_dir / filename, labels)

    _parse_bn_lut(bn_lut, labels)
    return labels


def build_manifest(
    mesh_dir: Path | str,
    out_file: Path | str,
    labels: dict[str, str] | None = None,
) -> dict:
    """Scan ``mesh_dir`` for 3D meshes, compute metadata, and write ``out_file``."""
    mesh_root = Path(mesh_dir).resolve()
    if not mesh_root.is_dir():
        raise FileNotFoundError(f"Mesh directory does not exist: {mesh_root}")

    label_map = load_anatomical_labels() if labels is None else labels

    mesh_files = sorted(
        (
            p for p in mesh_root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda p: p.relative_to(mesh_root).as_posix(),
    )

    assets: list[dict[str, object]] = []
    for mesh_path in mesh_files:
        asset_id = mesh_path.stem
        rel_path = mesh_path.relative_to(mesh_root).as_posix()
        assets.append(
            {
                "id": asset_id,
                "name": label_map.get(asset_id, asset_id),
                "format": mesh_path.suffix.lstrip(".").lower(),
                "relative_path": rel_path,
                "size_bytes": mesh_path.stat().st_size,
                "sha256": sha256_of(mesh_path),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "total_assets": len(assets),
        "assets": assets,
    }

    output_path = Path(out_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
# MedVerse Asset Ingestion (v0.2) — Generic, Config-Driven 3D Pipeline

Source-independent 11-stage core → dataset adapters (`BodyParts3D`, `Human Brainnetome`, …) → ontology selection → geometry cleanup & Quest 3 decimation → rigid/ICP registration → integrated Blender scene → independent **BLEND**, **FBX** (Unity), and **Draco GLB** (3D Web Viewer) exports + one canonical **`manifest.json`** with SHA-256 checksums.

## Quick Start

```bash
# 1. Install package with decimation, NIfTI, and test tools
pip install -e ".[dev,decimate,nifti]"

# 2. Download & verify BodyParts3D v4.0 (atomic .part streaming + Zip Slip guard)
python scripts/downloaders/bodyparts3d.py
python scripts/downloaders/bodyparts3d.py --verify-only

# 3. Verify Brainnetome Atlas files placed in data/raw/brainnetome/{atlas,labels}
python scripts/downloaders/check_brainnetome.py

# 4. Run pipeline
medverse selection --profile brain_spine                     # stages 1-4 audit only
medverse run       --profile quest3_lod0 --blender blender   # Meta Quest 3 VR build (<180k tris, BLEND+FBX+GLB)
medverse run       --profile brain_spine --blender blender   # high-res desktop build
medverse run       --profile legacy_parity --skip-export     # reproduces v1 selection choices
medverse run       --disable brainnetome                     # single-source run

# 5. Lint & test
ruff check src scripts tests
pytest -v
```

Exit codes: `0` all stages ok · `2` partial (e.g. Blender missing or some meshes skipped) · `1` a stage failed · `3` bad config.

## Outputs (`data/processed/run/`)

- **`final/`**: `anatomical_model_quest3_lod0.{blend,fbx,glb}` (or `anatomical_model.*`), plus one canonical **`manifest.json`** (FMA/Brainnetome ontology metadata, mesh stats, output byte sizes & SHA-256 checksums).
- **`reports/`**: `pipeline_report.json`, `selection_review.csv`, `asset_manifest.json`, `manifest.json`, `transform_manifest.json`, `geometry_report.json`, `registration_report.json`, `export_report.json`, `diagnostics.log`, `config_snapshot.json`.
- **`scene/`**: `spec.json` and per-object binary PLY meshes.

## Documentation

Start at [`docs/README.md`](docs/README.md) — covers upstream licensing & attribution (`docs/data/sources_and_licensing.md`), data layout (`docs/data/download_and_layout.md`), BodyParts3D tables (`docs/data/data_dictionary.md`), the 246-region Brainnetome guide (`docs/data/brainnetome_atlas.md`), FMA/BP/FJ ontology (`docs/ontology/foundational_model.md`), Meta Quest 3 budgets, and v0.2 architecture (`docs/ARCHITECTURE.md`, `docs/MIGRATION.md`).

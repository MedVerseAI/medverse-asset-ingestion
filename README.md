# MedVerse Asset Ingestion (v0.2) — generic, config-driven

Source-independent core → adapters (BodyParts3D, Brainnetome, …) → selection → geometry/registration → integrated
Blender scene → independent **BLEND** and **FBX** (Unity) exports, with failure-safe reports.

```bash
pip install -e ".[dev]"            # numpy, scipy, scikit-image  (+ optional nibabel, fast-simplification)
# data layout is unchanged:  data/raw/bodyparts3d/metadata, data/interim/bodyparts3d/obj_*, data/raw/brainnetome/{atlas,labels}

medverse selection  --profile brain_spine                         # stages 1-4 only: audit what would be selected
medverse run        --profile brain_spine --blender "E:\Programs\blender\blender.exe"
medverse run        --profile legacy_parity --skip-export         # reproduces the old pipeline's choices
medverse run --disable brainnetome                                # single-source run
python tests/run_all.py                                           # or: pytest
```
Exit code: `0` all stages ok · `2` partial (e.g. Blender missing, some meshes skipped) · `1` a stage failed · `3` bad config.

Outputs (`data/processed/run/`): `reports/` (pipeline_report.json, selection_review.csv, asset_manifest.json,
transform_manifest.json, geometry_report.json, registration_report.json, export_report.json, diagnostics.log,
config_snapshot.json), `scene/` (spec + meshes), `final/anatomical_model.blend`, `final/anatomical_model.fbx`.

Docs: `docs/ARCHITECTURE.md` (contracts, config keys) · `docs/MIGRATION.md` (legacy → new map, parity evidence, deviations).

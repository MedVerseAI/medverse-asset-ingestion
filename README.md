# medverse-asset-ingestion
Data ingestion, FMA ontology parsing, and 3D asset processing pipeline for BodyParts3D and the Human Brainnetome atlas.

## Quick start

```bash
pip install -e ".[export,dev]"
python scripts/downloaders/bodyparts3d.py          # BodyParts3D (automatic)
python scripts/downloaders/check_brainnetome.py    # after manual Brainnetome download

# choose what the Blender model contains (configs/default.toml, or the options below)
python scripts/run_pipeline.py --mode brainnetome --blender "E:\Programs\blender\blender.exe"  # cerebral cortex only (Brainnetome)
python scripts/run_pipeline.py --mode bodyparts3d --blender "E:\Programs\blender\blender.exe"  # brain parts + spine + BodyParts3D cortex
python scripts/run_pipeline.py --mode integrated  --blender "E:\Programs\blender\blender.exe"  # Brainnetome cortex + brain parts + spine (default)
#   --blender "E:\Programs\blender\blender.exe"  --skip-export  --dry-run  --print-config
```

The steps can still be run one by one (a step that the configured mode does not need skips itself):

```bash
python scripts/pipeline/01_export_bodyparts3d.py
python scripts/pipeline/02_export_bna_voxels.py
blender --background --python scripts/pipeline/03_integrate_brainnetome_bodyparts3d.py -- --mode integrated
```

Everything tunable lives in `configs/` (TOML, validated). Personal settings go into `configs/local.toml`
(see `configs/local.toml.example`). Details: `docs/pipeline/configuration.md`.
See `docs/` for the rest (start with `docs/README.md` and `docs/pipeline/processing_pipeline.md`).

# medverse-asset-ingestion
Data ingestion, FMA ontology parsing, and 3D asset processing pipeline for BodyParts3D dataset.

## Quick start

```bash
pip install -e ".[export,dev]"
python scripts/downloaders/bodyparts3d.py          # BodyParts3D (automatic)
python scripts/downloaders/check_brainnetome.py    # after manual Brainnetome download
python scripts/pipeline/01_export_bodyparts3d.py
python scripts/pipeline/02_export_bna_voxels.py
blender --background --python scripts/pipeline/03_integrate_brainnetome_bodyparts3d.py
```

See `docs/` for details (start with `docs/README.md` and `docs/pipeline/processing_pipeline.md`).

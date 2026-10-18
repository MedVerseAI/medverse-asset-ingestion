# Processing pipeline

```
download (BodyParts3D, automatic)      check_brainnetome (manual download)
        |                                        |
        v                                        v
01_export_bodyparts3d.py             02_export_bna_voxels.py        <- independent of each other
        |                                        |
        +------------------+---------------------+
                           v
        03_integrate_brainnetome_bodyparts3d.py   (runs inside Blender)
```

| Step | Command | Reads | Writes |
|---|---|---|---|
| 0a | `python scripts/downloaders/bodyparts3d.py` | web | `data/raw/bodyparts3d/`, `data/interim/bodyparts3d/obj_*` |
| 0b | `python scripts/downloaders/check_brainnetome.py` | `data/raw/brainnetome/` | `checksums.sha256` |
| 01 | `python scripts/pipeline/01_export_bodyparts3d.py` | `raw/bodyparts3d/metadata`, `interim/bodyparts3d/obj_*` | `interim/bodyparts3d/export_pieces/{meshes,reference,manifest.json}`, report |
| 02 | `python scripts/pipeline/02_export_bna_voxels.py` | `raw/brainnetome/atlas/BNA_MPM_thr25_1.25mm.nii.gz`, `labels/BN_Atlas_246_LUT.txt` | `interim/brainnetome/voxel_export_pieces/*.ply`, report |
| 03 | `blender --background --python scripts/pipeline/03_integrate_brainnetome_bodyparts3d.py` | outputs of 01 and 02 | `processed/final/anatomical_model.blend`, report |

Steps 01 and 02 do not depend on each other. Step 03 needs both. `make pipeline` runs 01, 02, 03 in order.

## Reports
All reports are in `data/processed/reports/`: `export_bodyparts3d_report.txt`, `export_bna_voxels_report.txt`, `integration_report.txt`.

## Interim folders
- `export_pieces/meshes/<GROUP>/*.ply`: cleaned BodyParts3D structures, one file per structure.
- `export_pieces/reference/cortex_reference_points.npz`: point cloud of the BodyParts3D cortex, used **only** for registration (never added to the model).
- `export_pieces/manifest.json`: structure list that step 03 reads.

## Code layout
- `medverse.paths`: every path (one place). `medverse.anatomy.config`: all settings.
- `medverse.anatomy.helpers/classes`: pure Python, bpy is optional. `medverse.integration.*`: registration and scene building; only the scene-building code needs `bpy`.
- Scripts add `src/` to `sys.path` themselves, so `pip install -e .` is optional. Inside Blender's Text Editor set `MEDVERSE_ROOT` first.

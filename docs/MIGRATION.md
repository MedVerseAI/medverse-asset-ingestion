# Migration: v1 (PR #9) → v0.2

The v1 pipeline (PR #9, `feat/integrate-brainnetome-bodyparts3d`) is preserved intact in Git history; the broken `tools/legacy_dump.py` and `tools/parity_selection.py` wrappers (which required an uncommitted `legacy/` directory) have been retired.

| Legacy (v1 / PR #9) | v0.2 Architecture |
|---|---|
| `scripts/pipeline/01_export_bodyparts3d.py` | `adapters/bodyparts3d`, `selection/*`, `geometry/{normalization,cleanup}` |
| `scripts/pipeline/02_export_bna_voxels.py` | `adapters/brainnetome`, `geometry/extraction.py` |
| `scripts/pipeline/03_integrate_*.py` | `geometry/registration.py`, `scene/{organization,builder}`, `exporters/{blender,fbx,glb}.py` |
| `anatomy/config.py` regex/constants | `configs/default.toml` (`[semantic.*]`, `[selection]`, `[geometry]`) |
| `anatomy/classes.py Metadata` | `adapters/bodyparts3d` (+ generic `selection/ontology.py`) |
| `settings.py` | `config.py` (while `paths.py` remains preserved for downloader scripts) |
| `scripts/run_pipeline.py --mode …` | `medverse run --profile …` (`brain_spine`, `quest3_lod0`, `legacy_parity`) |
| Standalone `04_generate_manifest.py` | Built-in canonical `manifest.json` (`reporting/manifest.py`) |

## Intentional behaviour changes (`brain_spine` & `quest3_lod0`)
1. Brainnetome owns cortical **and** subcortical regions (all 246); BodyParts3D thalamus/basal ganglia/amygdala/hippocampus become registration references (`legacy_parity` restores the old split).
2. Registration: no scale by default; BodyParts3D is moved into the atlas frame (affine untouched). Legacy bbox `fit_inside` scaling is available only via explicit `allow_scale = true` + `scale_reason`.
3. Label/affine left-right contradiction is validated and mirrored only with a logged `mirror` transform (`sources.brainnetome.on_lr_mismatch`).
4. Quest 3 optimization (`--profile quest3_lod0`): decimates Marching Cubes and BodyParts3D meshes under a strict `< 180,000` global triangle ceiling, consolidates materials via `scene.material_mode = "lobe_palette"`, and exports compressed `.blend`, Unity `.fbx`, Draco `.glb`, and canonical `manifest.json` in one pass.
5. Shared custom properties: Blender/GLB objects emit canonical keys (`group`, `side`, `label`, `ontology_ids`, `source`) alongside backward-compatible viewer aliases (`bp3d_group`, `hemisphere`, `bn_region_id`, `bn_region_name`).

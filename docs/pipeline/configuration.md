# Configuration and build modes

The pipeline is driven by TOML files in `configs/`. Nothing needs to be edited in Python to choose
what ends up in the Blender model.

## The three modes

| `mode` | Final `.blend` contains | Steps run | Output file |
|---|---|---|---|
| `brainnetome` | Cerebral cortex only (Brainnetome, 210 cortical regions, one object each) | 02 → 03 | `final/anatomical_model_brainnetome.blend` |
| `bodyparts3d` | BodyParts3D brain parts (cerebellum, brainstem, deep structures, ventricles, white matter) + spine (vertebrae, discs, cord) + **BodyParts3D's own cortex** (36 gyri/lobes) | 01 → 03 | `final/anatomical_model_bodyparts3d.blend` |
| `integrated` (default) | Brainnetome cortex + BodyParts3D brain parts + spine, registered together (BodyParts3D's cortex is used only as a registration reference) | 01, 02 → 03 | `final/anatomical_model.blend` (unchanged name) |

Reports follow the same naming: `reports/integration_report[_<mode>].txt`.

## Choosing the mode

```bash
# 1. one command, runs exactly the steps the mode needs
python scripts/run_pipeline.py --mode brainnetome
python scripts/run_pipeline.py --mode bodyparts3d
python scripts/run_pipeline.py --mode integrated --blender "E:/Programs/blender/blender.exe"

# 2. or through make
make build MODE=brainnetome
make build PROFILE=configs/profiles/bodyparts3d.toml

# 3. or run a single step by hand (a step the mode does not need skips itself)
python scripts/pipeline/01_export_bodyparts3d.py --mode bodyparts3d
blender --background --python scripts/pipeline/03_integrate_brainnetome_bodyparts3d.py -- --mode bodyparts3d
```

Useful switches of `run_pipeline.py`: `--skip-export` (reuse the interim files, only rebuild the `.blend`),
`--dry-run` (print the commands), `--print-config` (show the resolved settings as JSON).

## Resolution order (later wins)

1. `configs/default.toml`: declares **every** key with its default and a comment.
2. `configs/local.toml`: optional personal file, git-ignored (copy `configs/local.toml.example`).
3. `--config FILE` or `MEDVERSE_CONFIG`: a file path, or the name of a profile in `configs/profiles/`.
4. `--mode MODE` or `MEDVERSE_MODE`.

Only list the keys you want to change in your own file; everything else is inherited.
Unknown keys, wrong types and out-of-range values stop the run with a precise message
(for example `[brainnetome] smooth_sigma must be a number`), so typos never pass silently.

## What can be configured

| Section | Keys (see `default.toml` for all) |
|---|---|
| `[model]` | `mode` |
| `[blender]` | `executable` |
| `[brainnetome]` | `cortical_max_id`, `region_gap_scale`, `smooth_sigma`, `min_voxels`, `expected_regions`, `mpm_filename` |
| `[bodyparts3d]` | `include_cortex`, `include_ventricular_system`, `include_cerebral_white_matter`, `include_cranial_nerves`, **`enabled_groups`**, geometry cleaning / decimation, `[bodyparts3d.face_budget]` |
| `[registration]` | ICP and manual scale / rotation / translation overrides (integrated mode only) |
| `[scene]` | `root_name`, `units_per_mm`, `center_on`, `clear_previous_model`, `clean_scene_for_final_blend` |
| `[viewport]` | `shading`, `hide_grid`, `euler_deg`, `distance_factor` |

### Dropping parts of the BodyParts3D model

`enabled_groups` selects which groups reach the model. Example: brain-only model without the spine
(`configs/local.toml`):

```toml
[model]
mode = "bodyparts3d"

[bodyparts3d]
enabled_groups = ["CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES", "OTHER_BRAIN_STRUCTURES", "CEREBRAL_CORTEX"]
```

Valid groups: `CEREBELLUM`, `BRAINSTEM`, `SUBCORTICAL_STRUCTURES`, `OTHER_BRAIN_STRUCTURES`, `CRANIAL_NERVES`,
`VERTEBRAE`, `INTERVERTEBRAL_DISCS`, `SPINAL_CORD`, `CEREBRAL_CORTEX` (the last one only has an effect in
mode `bodyparts3d`; set `include_cortex = false` to leave it out there as well).

## How it is wired (for developers)

```
configs/*.toml ──► medverse/settings.py ──► medverse/anatomy/config.py  (legacy constant names, unchanged)
   validate + merge        apply(globals())      └─► helpers / classes / integration / scripts (unchanged imports)
```

* `settings.py` is the only place that translates `mode` into behaviour (`USE_BRAINNETOME`, `USE_BODYPARTS3D`,
  `EXPORT_BP3D_CORTEX`, `ENABLED_BP3D_GROUPS`). Modules never compare mode strings themselves.
* Each script calls `settings.configure_from_argv()` before importing `medverse.anatomy.config`; inside Blender only the
  arguments after `--` are read.
* Output file names depend on the mode via `paths.final_blend_for(mode)` / `paths.integration_report_for(mode)`;
  the folder layout under `data/` is unchanged.
* A stale interim export never leaks into the wrong model: step 03 ignores BodyParts3D cortex pieces in
  `integrated` mode and warns if `bodyparts3d` mode finds a manifest exported without the cortex.
* Python 3.10 (Blender 3.x) needs the `tomli` package; Python 3.11+ (Blender 4.x) uses the built-in `tomllib`.

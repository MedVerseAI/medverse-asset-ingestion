# Migration: legacy → new

`legacy/` holds the untouched old project (kept until equivalence is accepted — phase 10).

| Legacy | New |
|--------|-----|
| `scripts/pipeline/01_export_bodyparts3d.py` | `adapters/bodyparts3d`, `selection/*`, `geometry/{normalization,cleanup}` |
| `scripts/pipeline/02_export_bna_voxels.py` | `adapters/brainnetome`, `geometry/extraction.py` |
| `scripts/pipeline/03_integrate_*.py` | `geometry/registration.py`, `scene/{organization,builder}`, `exporters/*` |
| `anatomy/config.py` regex/constants | `configs/default.toml` (`[semantic.*]`, `[selection]`, `[geometry]`) |
| `anatomy/classes.py Metadata` | `adapters/bodyparts3d` (+ generic `selection/ontology.py`) |
| `settings.py`, `paths.py` | `config.py` |
| `scripts/run_pipeline.py --mode …` | `medverse run --profile …` (`brain_spine`, `legacy_parity`) |

## Equivalence evidence (run: `python tools/parity_selection.py`)
On the real BodyParts3D metadata: the old `classify_all` classified 155 in-scope elements; the new engine under
`legacy_parity` reproduces every decision (include+group / ambiguous→review / cortex→reference / muscle→excluded):
**0 mismatches, 0 extra inclusions** (also asserted in `tests/test_selection.py`).
Mesh-level equivalence (needs your OBJ/NIfTI files): run both pipelines and compare object names/counts/bboxes —
not possible in the environment this was built in (see Limitations).

## Intentional behaviour changes (profile `brain_spine`)
1. Brainnetome owns cortical **and** subcortical regions (all 246); BodyParts3D thalamus/basal ganglia/amygdala/
   hippocampus become registration references. `legacy_parity` restores the old split.
2. Registration: no scale by default; BodyParts3D is moved into the atlas frame (affine untouched). Legacy used a
   bbox `fit_inside` scale — available only via `allow_scale=true` + reason (see `legacy_parity`).
3. Label/affine left-right contradiction is validated and mirrored only with a logged `mirror` transform
   (`sources.brainnetome.on_lr_mismatch`).
4. Not ported: BodyParts3D `mesh_source = "concept"` (BPxxxx) mode — only element (FJ) meshes.

## Removal checklist (phase 10)
[ ] run `legacy_parity` on real data and diff against the old `.blend` · [ ] open BLEND/FBX in Blender/Unity ·
[ ] then delete `legacy/`.

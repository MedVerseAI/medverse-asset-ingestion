# Architecture (implements the Architectural Specification)

## Pipeline contract (`core/pipeline.py`)
| # | Stage | Input → Output |
|---|-------|----------------|
| 1 | configuration | TOML layers → validated config + `config_snapshot.json` (sha256) |
| 2 | discovery | config → available sources, file list + sha256 |
| 3 | adapters | sources → `SourceEntity` list, `Ontology`, relations (metadata only, no geometry) |
| 4 | selection | entities → `Decision` per entity → `selection_review.csv` |
| 5 | normalization | selected entities → `MeshAsset` / `VolumeAsset`; raw units/axes → RAS mm (logged transforms) |
| 6 | geometry | volumes → surfaces (extraction), mesh cleanup, decimation |
| 7 | registration | spatial metadata → landmarks → reference geometry → ICP; `allow_scale=false` |
| 8 | integration | final assets → `scene/spec.json` + Blender scene build |
| 9 | validation | geometry, selection, alignment, orientation, units, NIfTI affine, duplicates |
| 10 | export | independent BLEND and FBX (each its own Blender process + verification by re-opening / re-importing) |
| 11 | reporting | all reports (also flushed after every stage and in `finally`) |

A failed stage never deletes evidence: dependants are `skipped` with the reason; independent work continues;
per-source status is kept for every stage.

## Asset model (`core/assets.py`)
`BaseAsset(metadata, transform, provenance, coordinate_system)` → `MeshAsset | VolumeAsset | PointCloudAsset`.
A NIfTI stays a `VolumeAsset` (affine untouched, checked) until `geometry/extraction.py` decides to extract a surface.

## Selection priority (`selection/resolver.py`)
explicit exclusion → explicit inclusion → ontology/semantic rule (scope + regex, per source, in config) →
configured name fallback (`fallback_used=true`) → unknown ⇒ **review** (never auto-included).
Ownership/overlap: `[[profile.targets]]` (`owner`, `fallback_owner`, `policy`, `enabled_by`,
`reference_for_registration`). A non-owner copy becomes a registration `reference`, not a scene object.
Disc/vertebra/cord inclusion: `anatomy.spine.include_*`.

## Adding a source
Subclass `SourceAdapter`, decorate with `@register_adapter("name")`, add `[sources.name]`, `[semantic.name]`
rules and profile targets. No change to `core/`, `selection/`, `geometry/registration.py`, `scene/` or exporters.

## Registration (`geometry/registration.py`)
T0 = identity (both sides already RAS mm via affine / inferred frame) → landmark Kabsch (rigid) → cloud measure →
trimmed rigid ICP (rotation/translation bounded, accepted only if RMS improves). The moving source (default
BodyParts3D) is moved into the atlas frame, so the NIfTI affine is never modified. A scale needs
`allow_scale=true` + `scale_reason`; it is recorded as a `scale` transform and checked by validation.

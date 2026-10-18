"""
src/medverse/settings.py

User-facing configuration of the pipeline (TOML) with validation.

Why a separate layer?
    medverse/anatomy/config.py keeps every tunable constant under its historical name, so all
    existing modules keep working unchanged.  This module only decides the *values*:
    it reads configs/default.toml, merges optional overrides, validates them, and
    `apply(namespace)` writes them into anatomy/config.py's namespace.

Resolution order (later wins)
    1. configs/default.toml          every key must be declared here
    2. configs/local.toml            optional personal file (git-ignored)
    3. --config FILE|PROFILE         or env MEDVERSE_CONFIG   (PROFILE = name in configs/profiles/)
    4. --mode MODE                   or env MEDVERSE_MODE

Modes (what the final .blend contains)
    brainnetome  : cerebral cortex only (Brainnetome)
    bodyparts3d  : BodyParts3D only (brain parts + spine + its own cortex)
    integrated   : Brainnetome cortex + BodyParts3D brain parts + spine, registered together

Pure Python (needs `tomllib`, i.e. Python >= 3.11, or the `tomli` backport).
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:                                    # Python >= 3.11
    import tomllib as _toml
except ModuleNotFoundError:             # Python 3.10 (e.g. Blender 3.x): pip install tomli
    try:
        import tomli as _toml           # type: ignore[no-redef]
    except ModuleNotFoundError:         # pragma: no cover
        _toml = None

from medverse import paths

ENV_CONFIG = "MEDVERSE_CONFIG"
ENV_MODE = "MEDVERSE_MODE"

MODES = ("brainnetome", "bodyparts3d", "integrated")
BP3D_GROUPS = (
    "CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES", "OTHER_BRAIN_STRUCTURES", "CRANIAL_NERVES",
    "VERTEBRAE", "INTERVERTEBRAL_DISCS", "SPINAL_CORD", "CEREBRAL_CORTEX",
)

# pipeline steps each mode needs (steps 01 / 02 are plain Python, 03 runs inside Blender)
MODE_STEPS = {
    "brainnetome": ("02", "03"),
    "bodyparts3d": ("01", "03"),
    "integrated": ("01", "02", "03"),
}


class SettingsError(ValueError):
    """Invalid configuration (unknown key, wrong type, value out of range ...)."""


# ============================================================================
# Validation
# ============================================================================
_ENUMS = {
    "model.mode": MODES,
    "bodyparts3d.mesh_source": ("element", "concept", "auto"),
    "registration.scale_mode": ("fit_inside", "match_mean"),
    "scene.center_on": ("model_bbox", "cortex_bbox"),
    "viewport.shading": ("SOLID", "MATERIAL"),
}
_RANGES = {                                         # key -> (min, max) inclusive, None = open
    "brainnetome.cortical_max_id": (1, 246),
    "brainnetome.region_gap_scale": (0.5, 1.5),
    "brainnetome.smooth_sigma": (0.0, None),
    "brainnetome.min_voxels": (1, None),
    "bodyparts3d.default_face_budget": (100, None),
    "bodyparts3d.weld_tolerance_mm": (0.0, None),
    "registration.icp_trim_fraction": (0.1, 1.0),
    "registration.max_rotation_deg": (0.0, 180.0),
    "scene.units_per_mm": (1e-6, 1e3),
    "viewport.distance_factor": (0.1, 100.0),
}
_FREE_LENGTH_LISTS = {"bodyparts3d.enabled_groups", "bodyparts3d.ambiguous_include_patterns"}
_FREE_TABLES = {"bodyparts3d.face_budget"}          # tables whose keys are not fixed by the defaults


def _check_value(dotted: str, value: Any, default: Any, source: str) -> Any:
    def bad(msg):
        raise SettingsError(f"{source}: [{dotted}] {msg}")

    if isinstance(default, bool):
        if not isinstance(value, bool):
            bad(f"must be true/false, got {value!r}")
    elif isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            bad(f"must be an integer, got {value!r}")
    elif isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            bad(f"must be a number, got {value!r}")
        value = float(value)
    elif isinstance(default, str):
        if not isinstance(value, str):
            bad(f"must be a string, got {value!r}")
    elif isinstance(default, list):
        if not isinstance(value, list):
            bad(f"must be a list, got {value!r}")
        if dotted not in _FREE_LENGTH_LISTS and len(value) != len(default):
            bad(f"must have {len(default)} items, got {len(value)}")
        if default:
            value = [_check_value(f"{dotted}[{i}]", v, default[0], source) for i, v in enumerate(value)]
    if dotted in _ENUMS and value not in _ENUMS[dotted]:
        bad(f"must be one of {list(_ENUMS[dotted])}, got {value!r}")
    if dotted in _RANGES:
        lo, hi = _RANGES[dotted]
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            bad(f"must be within [{lo}, {hi}], got {value!r}")
    if dotted == "bodyparts3d.enabled_groups":
        unknown = sorted(set(value) - set(BP3D_GROUPS))
        if unknown:
            bad(f"unknown group(s) {unknown}; valid: {list(BP3D_GROUPS)}")
    return value


def _merge(base: dict, over: dict, source: str, prefix: str = "") -> None:
    """Deep-merge `over` into `base` in place, validating every key against `base` (= the defaults)."""
    for key, value in over.items():
        dotted = f"{prefix}{key}"
        if key not in base:
            if prefix.rstrip(".") in _FREE_TABLES:
                if key not in BP3D_GROUPS:
                    raise SettingsError(f"{source}: [{dotted}] unknown group; valid: {list(BP3D_GROUPS)}")
                base[key] = _check_value(dotted, value, 1, source)
                continue
            known = ", ".join(sorted(base)) or "-"
            raise SettingsError(f"{source}: unknown key [{dotted}] (known here: {known})")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise SettingsError(f"{source}: [{dotted}] must be a table")
            _merge(base[key], value, source, dotted + ".")
        else:
            base[key] = _check_value(dotted, value, base[key], source)


def _read_toml(path: Path) -> dict:
    if _toml is None:
        raise SettingsError("no TOML parser: use Python >= 3.11 or `pip install tomli` "
                            "(inside Blender 3.x: install it into Blender's Python)")
    try:
        with open(path, "rb") as fh:
            return _toml.load(fh)
    except FileNotFoundError:
        raise SettingsError(f"config file not found: {path}") from None
    except _toml.TOMLDecodeError as exc:
        raise SettingsError(f"{path}: invalid TOML ({exc})") from None


def resolve_config_path(spec: str) -> Path:
    """`spec` may be a path (absolute / cwd-relative / repo-relative) or a profile name."""
    p = Path(spec).expanduser()
    for cand in (p, paths.ROOT / p, paths.PROFILES / p, paths.PROFILES / f"{spec}.toml"):
        if cand.is_file():
            return cand.resolve()
    raise SettingsError(f"config '{spec}' not found (tried as path and as profile in {paths.PROFILES})")


# ============================================================================
# Settings object
# ============================================================================
@dataclass(frozen=True)
class Settings:
    raw: dict
    sources: tuple = field(default_factory=tuple)

    # ---- mode ----
    @property
    def mode(self) -> str:
        return self.raw["model"]["mode"]

    @property
    def use_brainnetome(self) -> bool:
        return self.mode in ("brainnetome", "integrated")

    @property
    def use_bodyparts3d(self) -> bool:
        return self.mode in ("bodyparts3d", "integrated")

    @property
    def export_bp3d_cortex(self) -> bool:
        """BodyParts3D's own cortex is exported/imported ONLY in standalone BodyParts3D mode."""
        return self.mode == "bodyparts3d" and self.raw["bodyparts3d"]["include_cortex"]

    @property
    def bp3d_groups(self) -> tuple:
        groups = tuple(self.raw["bodyparts3d"]["enabled_groups"])
        return groups if self.export_bp3d_cortex else tuple(g for g in groups if g != "CEREBRAL_CORTEX")

    @property
    def steps(self) -> tuple:
        return MODE_STEPS[self.mode]

    def needs_step(self, step: str) -> bool:
        return step in self.steps

    def describe(self) -> str:
        what = {"brainnetome": "Brainnetome cerebral cortex only",
                "bodyparts3d": "BodyParts3D brain parts + spine + own cortex",
                "integrated": "Brainnetome cortex + BodyParts3D brain parts + spine"}[self.mode]
        return f"mode '{self.mode}' ({what}); steps {', '.join(self.steps)}"


# ============================================================================
# Loading
# ============================================================================
_overrides: dict = {"config": None, "mode": None}
_cache: Optional[Settings] = None


def configure(config: Optional[str] = None, mode: Optional[str] = None) -> None:
    """Set explicit overrides (CLI) and forget any cached settings. Also exported to the environment."""
    global _cache
    _overrides["config"], _overrides["mode"] = config, mode
    if config:
        os.environ[ENV_CONFIG] = config
    if mode:
        os.environ[ENV_MODE] = mode
    _cache = None


def reload() -> Settings:
    global _cache
    _cache = None
    return get()


def load(config: Optional[str] = None, mode: Optional[str] = None) -> Settings:
    """Build Settings from files + overrides (no caching, no environment access except the defaults below)."""
    config = config or os.environ.get(ENV_CONFIG) or None
    mode = mode or os.environ.get(ENV_MODE) or None
    raw = _read_toml(paths.DEFAULT_CONFIG)
    sources = [paths.DEFAULT_CONFIG]
    layers = []
    if paths.LOCAL_CONFIG.is_file():
        layers.append(paths.LOCAL_CONFIG)
    if config:
        layers.append(resolve_config_path(config))
    for layer in layers:
        _merge(raw, _read_toml(layer), str(layer))
        sources.append(layer)
    if mode:
        _merge(raw, {"model": {"mode": mode}}, "--mode / MEDVERSE_MODE")
    return Settings(raw=raw, sources=tuple(sources))


def get() -> Settings:
    global _cache
    if _cache is None:
        _cache = load(_overrides["config"], _overrides["mode"])
    return _cache


def parse_argv(argv=None) -> argparse.Namespace:
    """Read --config / --mode. Unknown arguments are ignored (Blender passes its own).

    Plain Python:  script.py --mode brainnetome
    Blender     :  blender -b --python script.py -- --mode brainnetome   (only what follows `--` is read)
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--config")
    ap.add_argument("--mode", choices=MODES)
    ns, _ = ap.parse_known_args(argv)
    return ns


def configure_from_argv(argv=None) -> Settings:
    """Entry point used by every pipeline script before it imports medverse.anatomy.config."""
    ns = parse_argv(argv)
    for name in [m for m in sys.modules if m == "medverse.anatomy" or m.startswith("medverse.anatomy.")
                 or m.startswith("medverse.integration")]:
        del sys.modules[name]                       # Blender keeps modules alive between runs
    configure(ns.config, ns.mode)
    return get()


# ============================================================================
# Binding to the legacy constant names of medverse.anatomy.config
# ============================================================================
def _t(x):
    return tuple(x)


# (section, key, CONSTANT, transform)
_MAPPING: list = [
    ("brainnetome", "cortical_max_id", "BN_CORTICAL_MAX_ID", None),
    ("brainnetome", "region_gap_scale", "BN_REGION_GAP_SCALE", None),
    ("brainnetome", "smooth_sigma", "BN_SMOOTH_SIGMA", None),
    ("brainnetome", "min_voxels", "BN_MIN_VOXELS", None),
    ("brainnetome", "expected_regions", "BN_EXPECTED_REGIONS", None),
    ("brainnetome", "mpm_filename", "BN_MPM_FILENAME", None),
    ("bodyparts3d", "mesh_source", "MESH_SOURCE", None),
    ("bodyparts3d", "include_ventricular_system", "INCLUDE_VENTRICULAR_SYSTEM", None),
    ("bodyparts3d", "include_cerebral_white_matter", "INCLUDE_CEREBRAL_WHITE_MATTER", None),
    ("bodyparts3d", "include_cranial_nerves", "INCLUDE_CRANIAL_NERVES", None),
    ("bodyparts3d", "ambiguous_include_patterns", "AMBIGUOUS_INCLUDE_PATTERNS", list),
    ("bodyparts3d", "weld_tolerance_mm", "WELD_TOLERANCE_MM", None),
    ("bodyparts3d", "component_min_fraction", "COMPONENT_MIN_FRACTION", None),
    ("bodyparts3d", "component_min_faces", "COMPONENT_MIN_FACES", None),
    ("bodyparts3d", "default_face_budget", "DEFAULT_FACE_BUDGET", None),
    ("bodyparts3d", "decimation_aggressiveness", "DECIMATION_AGGRESSIVENESS", None),
    ("bodyparts3d", "max_bbox_drift_mm", "MAX_BBOX_DRIFT_MM", None),
    ("bodyparts3d", "reference_point_count", "REFERENCE_POINT_COUNT", None),
    ("registration", "scale_mode", "REG_SCALE_MODE", None),
    ("registration", "use_icp", "REG_USE_ICP", None),
    ("registration", "sample_points", "REG_SAMPLE_POINTS", None),
    ("registration", "icp_iterations", "REG_ICP_ITERATIONS", None),
    ("registration", "icp_trim_fraction", "REG_ICP_TRIM_FRACTION", None),
    ("registration", "icp_scale_bounds", "REG_ICP_SCALE_BOUNDS", _t),
    ("registration", "max_rotation_deg", "REG_MAX_ROTATION_DEG", None),
    ("registration", "hard_scale_limits", "REG_HARD_SCALE_LIMITS", _t),
    ("registration", "manual_scale", "REG_MANUAL_SCALE", lambda v: v or None),   # 0 -> None (automatic)
    ("registration", "manual_translation_mm", "REG_MANUAL_TRANSLATION_MM", _t),
    ("registration", "manual_rotation_deg", "REG_MANUAL_ROTATION_DEG", _t),
    ("scene", "root_name", "ROOT_NAME", None),
    ("scene", "units_per_mm", "BLENDER_UNITS_PER_MM", None),
    ("scene", "orient_model_to_atlas", "ORIENT_MODEL_TO_ATLAS", None),
    ("scene", "center_on", "CENTER_ON", None),
    ("scene", "clear_previous_model", "CLEAR_PREVIOUS_MODEL", None),
    ("scene", "clean_scene_for_final_blend", "CLEAN_SCENE_FOR_FINAL_BLEND", None),
    ("viewport", "enabled", "SET_SOLID_MATERIAL_VIEWPORT", None),
    ("viewport", "shading", "VIEWPORT_SHADING", None),
    ("viewport", "hide_grid", "HIDE_VIEWPORT_GRID", None),
    ("viewport", "euler_deg", "VIEW_EULER_DEG", _t),
    ("viewport", "distance_factor", "VIEW_DISTANCE_FACTOR", None),
]


def apply(namespace: dict, settings: Optional[Settings] = None) -> Settings:
    """Write the configured values into `namespace` (the globals() of medverse.anatomy.config)."""
    s = settings or get()
    for section, key, const, transform in _MAPPING:
        value = copy.deepcopy(s.raw[section][key])
        namespace[const] = transform(value) if transform else value
    namespace.setdefault("FACE_BUDGET", {}).update(s.raw["bodyparts3d"]["face_budget"])
    # ---- derived flags (single place that translates `mode` into behaviour) ----
    namespace["SETTINGS"] = s
    namespace["MODE"] = s.mode
    namespace["USE_BRAINNETOME"] = s.use_brainnetome
    namespace["USE_BODYPARTS3D"] = s.use_bodyparts3d
    namespace["EXPORT_BP3D_CORTEX"] = s.export_bp3d_cortex
    namespace["ENABLED_BP3D_GROUPS"] = s.bp3d_groups
    namespace["BLENDER_EXECUTABLE"] = s.raw["blender"]["executable"]
    return s

"""Configuration: Load -> Merge -> Validate  (pipeline stage 1).

Resolution (later wins): default.toml -> profiles/<name>.toml -> local.toml -> --config -> overrides.
Dicts are merged recursively, lists are replaced.  Strict sections reject unknown keys / wrong types,
while dynamic `[sources.<plugin>]` adapter tables are permitted so new datasets plug in cleanly.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tomllib
from pathlib import Path

ENV_ROOT = "MEDVERSE_ROOT"
ENV_DATA = "MEDVERSE_DATA_DIR"

# sections whose key set is fixed by default.toml (free-form: selection, semantic, profile, anatomy, registration.landmarks)
STRICT = ("project", "sources", "geometry", "registration", "scene", "blender", "export", "reporting")
FREE_PATHS = {("registration", "landmarks"), ("geometry", "face_budget"), ("scene", "colors")}


class ConfigError(ValueError):
    pass


def find_root() -> Path:
    env = os.environ.get(ENV_ROOT)
    if env:
        return Path(env).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "configs" / "default.toml").is_file():
            return parent
    raise ConfigError(f"cannot locate repository root; set {ENV_ROOT}")


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _validate(defaults: dict, cfg: dict, path=()):
    for key, val in cfg.items():
        here = path + (key,)
        if not path and key not in defaults:
            continue                                        # free top-level sections (selection, semantic, ...)
        # Allow dynamic plugin source tables under `[sources.<new_atlas>]` without bypassing validation of built-in sources
        if path == ("sources",) and key not in defaults:
            if not isinstance(val, dict):
                raise ConfigError(f"{'.'.join(here)}: expected table/dict for plugin source, got {type(val).__name__}")
            continue
        if path and path[0] in STRICT and here not in FREE_PATHS and not any(here[:len(f)] == f for f in FREE_PATHS):
            if key not in defaults:
                raise ConfigError(f"unknown config key: {'.'.join(here)}")
        if key in defaults:
            d = defaults[key]
            if isinstance(d, dict) and isinstance(val, dict):
                _validate(d, val, here)
            elif isinstance(d, bool) != isinstance(val, bool) and not isinstance(d, (dict, list)):
                raise ConfigError(f"{'.'.join(here)}: expected {type(d).__name__}, got {type(val).__name__}")
            elif isinstance(d, (int, float)) and not isinstance(d, bool) and not isinstance(val, (int, float)):
                raise ConfigError(f"{'.'.join(here)}: expected number, got {type(val).__name__}")
            elif isinstance(d, str) and not isinstance(val, str):
                raise ConfigError(f"{'.'.join(here)}: expected string, got {type(val).__name__}")
            elif isinstance(d, list) and not isinstance(val, list):
                raise ConfigError(f"{'.'.join(here)}: expected list, got {type(val).__name__}")


def _semantic_checks(cfg: dict):
    r = cfg["registration"]
    if r["allow_scale"] and not str(r["scale_reason"]).strip():
        raise ConfigError("registration.allow_scale = true requires a non-empty registration.scale_reason "
                          "(every scale must be justified and is recorded in the transform provenance)")
    if cfg["selection"]["unknown_policy"] not in ("review", "exclude"):
        raise ConfigError("selection.unknown_policy must be 'review' or 'exclude' (never automatic inclusion)")
    bn_cfg = cfg["sources"].get("brainnetome")
    if isinstance(bn_cfg, dict) and "on_lr_mismatch" in bn_cfg:
        if bn_cfg["on_lr_mismatch"] not in ("mirror", "warn", "fail"):
            raise ConfigError("sources.brainnetome.on_lr_mismatch must be mirror|warn|fail")
    if cfg["scene"].get("material_mode", "per_region") not in ("per_region", "lobe_palette", "group"):
        raise ConfigError("scene.material_mode must be per_region|lobe_palette|group")
    if r["scale_init"] not in ("none", "fit_inside", "match_mean"):
        raise ConfigError("registration.scale_init must be none|fit_inside|match_mean")
    enabled = {n for n, s in cfg["sources"].items() if isinstance(s, dict) and s.get("enabled")}
    if r["moving_source"] not in cfg["sources"]:
        raise ConfigError(f"registration.moving_source '{r['moving_source']}' is not a configured source")
    names = set()
    for t in cfg.get("profile", {}).get("targets", []):
        for need in ("name", "categories", "owner"):
            if need not in t:
                raise ConfigError(f"profile target missing '{need}': {t}")
        if t["name"] in names:
            raise ConfigError(f"duplicate profile target '{t['name']}'")
        names.add(t["name"])
        pol = t.get("policy", "include")
        if pol not in ("include", "review", "reference"):
            raise ConfigError(f"profile target {t['name']}: bad policy {pol}")
        if pol == "include" and "group" not in t:
            raise ConfigError(f"profile target {t['name']}: policy include needs 'group'")
    for inc in cfg["selection"].get("inclusions", []):
        tgt = inc.get("target")
        if tgt and tgt not in names:
            raise ConfigError(f"inclusion {inc.get('id')}: unknown target '{tgt}'")
    if not enabled:
        raise ConfigError("no source is enabled")


def dotted(cfg: dict, key: str, default=None):
    cur = cfg
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def load_config(root: Path | None = None, profile: str | None = None, config_file: str | None = None,
                overrides: dict | None = None) -> dict:
    root = Path(root) if root else find_root()
    cfgdir = root / "configs"
    defaults = _read(cfgdir / "default.toml")
    layers = []
    local = _read(cfgdir / "local.toml") if (cfgdir / "local.toml").is_file() else {}
    explicit = {}
    if config_file:
        p = Path(config_file)
        if not p.is_file():
            p = cfgdir / "profiles" / (config_file if config_file.endswith(".toml") else config_file + ".toml")
        explicit = _read(p)
        layers.append(str(p))
    name = (profile or (overrides or {}).get("profile", {}).get("name") or explicit.get("profile", {}).get("name")
            or local.get("profile", {}).get("name") or defaults["profile"]["name"])
    ppath = cfgdir / "profiles" / f"{name}.toml"
    if not ppath.is_file():
        raise ConfigError(f"profile '{name}' not found: {ppath}")
    cfg = deep_merge(defaults, _read(ppath))
    cfg = deep_merge(cfg, local)
    cfg = deep_merge(cfg, explicit)
    cfg = deep_merge(cfg, overrides or {})
    cfg.setdefault("profile", {})["name"] = name
    _validate(defaults, cfg)
    _semantic_checks(cfg)
    data_dir = (cfg["project"]["data_dir"] or os.environ.get(ENV_DATA) or str(root / "data"))
    cfg["_runtime"] = {"root": str(root), "data_dir": str(Path(data_dir).expanduser().resolve()),
                       "layers": [str(cfgdir / "default.toml"), str(ppath)] +
                                 ([str(cfgdir / "local.toml")] if local else []) + layers}
    out = cfg["project"]["output_dir"] or str(Path(cfg["_runtime"]["data_dir"]) / "processed" / "run")
    cfg["_runtime"]["output_dir"] = str(Path(out).expanduser().resolve())
    return cfg


def snapshot(cfg: dict) -> dict:
    """JSON-safe snapshot + hash of the effective configuration (reproducibility)."""
    blob = json.dumps(cfg, sort_keys=True, default=str)
    return {"sha256": hashlib.sha256(blob.encode()).hexdigest(), "config": json.loads(blob)}

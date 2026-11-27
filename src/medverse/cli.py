"""Command line:  medverse run | selection | check-config"""
from __future__ import annotations

import argparse
import json
import sys

from medverse.config import ConfigError, load_config

SELECTION_ONLY_STAGES = ("configuration", "discovery", "adapters", "selection", "reporting")


def _overrides(a) -> dict:
    o = {}
    if a.out:
        o.setdefault("project", {})["output_dir"] = a.out
    if a.data:
        o.setdefault("project", {})["data_dir"] = a.data
    if a.blender:
        o.setdefault("blender", {})["executable"] = a.blender
    if getattr(a, "skip_export", False):
        o["export"] = {
            "blend": {"enabled": False},
            "fbx": {"enabled": False},
            "glb": {"enabled": False},
        }
    for s in (a.disable or []):
        o.setdefault("sources", {}).setdefault(s, {})["enabled"] = False
    return o


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="medverse")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "selection", "check-config"):
        s = sub.add_parser(name)
        s.add_argument("--profile", help="profile name (configs/profiles/<name>.toml)")
        s.add_argument("--config", help="extra TOML file or profile name")
        s.add_argument("--out", help="output directory")
        s.add_argument("--data", help="data directory")
        s.add_argument("--blender", help="Blender executable")
        s.add_argument("--disable", action="append", help="disable a source (repeatable)")
        s.add_argument("--skip-export", action="store_true")
        s.add_argument("--print-config", action="store_true")
    a = p.parse_args(argv)
    try:
        cfg = load_config(profile=a.profile, config_file=a.config, overrides=_overrides(a))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 3
    if a.print_config or a.cmd == "check-config":
        print(json.dumps(cfg, indent=1, default=str))
        return 0
    from medverse.core.pipeline import STAGES, Pipeline

    stages = [s for s in STAGES if s[0] in SELECTION_ONLY_STAGES] if a.cmd == "selection" else None
    return Pipeline(cfg, stages=stages).run()


if __name__ == "__main__":
    sys.exit(main())

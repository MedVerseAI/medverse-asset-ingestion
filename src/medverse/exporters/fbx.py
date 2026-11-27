"""FBX exporter for Unity -- independent of the BLEND export (own Blender process, own verification)."""
from __future__ import annotations

from pathlib import Path

from medverse.core.registry import register_exporter
from medverse.exporters.blender import run_blender


@register_exporter("fbx")
def export_fbx(ctx) -> dict:
    cfg = ctx.cfg
    ec = cfg["export"]["fbx"]
    if not ec["enabled"]:
        return {"status": "skipped", "reason": "disabled in config"}
    if not ctx.spec_path or not Path(ctx.spec_path).is_file():
        return {"status": "failed", "error": "scene spec does not exist; integration stage did not finish"}
    out = Path(ctx.out_dir) / "final" / ec["filename"]
    args = {"spec_path": str(ctx.spec_path), "work_blend": str(ctx.work_blend or ""), "out_fbx": str(out),
            "source": ec["source"], "axis_forward": ec["axis_forward"], "axis_up": ec["axis_up"],
            "apply_unit_scale": ec["apply_unit_scale"], "bake_space_transform": ec["bake_space_transform"],
            "verify_reimport": ec["verify_reimport"]}
    return run_blender(cfg, "fbx", args, Path(ctx.out_dir) / "work", ctx.diag)

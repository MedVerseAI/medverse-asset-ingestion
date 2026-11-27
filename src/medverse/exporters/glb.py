"""GLB (glTF 2.0 binary + Draco) exporter for web 3D viewer & dashboard -- own Blender subprocess + verification."""
from __future__ import annotations

from pathlib import Path

from medverse.core.registry import register_exporter
from medverse.exporters.blender import run_blender


@register_exporter("glb")
def export_glb(ctx) -> dict:
    cfg = ctx.cfg
    ec = cfg["export"]["glb"]
    if not ec["enabled"]:
        return {"status": "skipped", "reason": "disabled in config"}
    if not ctx.spec_path or not Path(ctx.spec_path).is_file():
        return {"status": "failed", "error": "scene spec does not exist; integration stage did not finish"}
    out = Path(ctx.out_dir) / "final" / ec["filename"]
    args = {
        "spec_path": str(ctx.spec_path),
        "work_blend": str(ctx.work_blend or ""),
        "out_glb": str(out),
        "source": ec["source"],
        "draco_compression": ec["draco_compression"],
        "draco_level": ec["draco_level"],
        "export_extras": ec["export_extras"],
        "verify_reimport": ec["verify_reimport"],
    }
    return run_blender(cfg, "glb", args, Path(ctx.out_dir) / "work", ctx.diag)

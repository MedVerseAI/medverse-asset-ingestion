"""BLEND exporter + the subprocess bridge to Blender (the only place that launches Blender)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from medverse.core.registry import register_exporter

ENTRY = Path(__file__).with_name("blender_entry.py")
SRC_DIR = str(Path(__file__).resolve().parents[2])


class BlenderUnavailable(RuntimeError):
    pass


def resolve_blender(cfg: dict) -> str:
    exe = cfg["blender"]["executable"] or os.environ.get("BLENDER") or shutil.which("blender")
    if not exe or not (Path(exe).is_file() or shutil.which(exe)):
        raise BlenderUnavailable("Blender executable not found (set [blender] executable, $BLENDER, or put blender on PATH)")
    return exe


def run_blender(cfg: dict, cmd: str, args: dict, work_dir: Path, diag=None) -> dict:
    exe = resolve_blender(cfg)
    work_dir.mkdir(parents=True, exist_ok=True)
    args = dict(args, src_dir=SRC_DIR, result_path=str(work_dir / f"blender_{cmd}_result.json"))
    apath = work_dir / f"blender_{cmd}_args.json"
    apath.write_text(json.dumps(args, indent=1), encoding="utf-8")
    if os.path.exists(args["result_path"]):
        os.remove(args["result_path"])
    proc = subprocess.run([exe, "-b", "--factory-startup", "--python", str(ENTRY), "--", cmd, str(apath)],
                          capture_output=True, text=True, timeout=cfg["blender"]["timeout_s"])
    (work_dir / f"blender_{cmd}.log").write_text((proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or ""),
                                                 encoding="utf-8")
    if os.path.isfile(args["result_path"]):
        res = json.loads(Path(args["result_path"]).read_text(encoding="utf-8"))
    else:
        res = {"cmd": cmd, "status": "failed", "error": f"Blender produced no result (exit {proc.returncode})"}
    res["returncode"] = proc.returncode
    if res["status"] != "ok" and diag:
        diag.error(f"blender {cmd}: {res.get('error', 'failed')}", stage="blender")
    return res


@register_exporter("blend")
def export_blend(ctx) -> dict:
    cfg = ctx.cfg
    ec = cfg["export"]["blend"]
    if not ec["enabled"]:
        return {"status": "skipped", "reason": "disabled in config"}
    out = Path(ctx.out_dir) / "final" / ec["filename"]
    if not ctx.work_blend or not Path(ctx.work_blend).is_file():
        return {"status": "failed", "error": "integrated scene (.blend) does not exist; integration stage did not finish"}
    return run_blender(cfg, "finalize", {"spec_path": str(ctx.spec_path), "work_blend": str(ctx.work_blend),
                                         "out_blend": str(out)}, Path(ctx.out_dir) / "work", ctx.diag)

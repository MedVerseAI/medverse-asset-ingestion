"""
run_pipeline.py        (plain Python:  python scripts/run_pipeline.py --mode brainnetome)
---------------
One command that runs exactly the steps the chosen mode needs, in order:

    mode          steps          result
    brainnetome   02 -> 03       Brainnetome cerebral cortex only
    bodyparts3d   01 -> 03       BodyParts3D brain parts + spine + own cortex
    integrated    01, 02 -> 03   Brainnetome cortex + BodyParts3D brain parts + spine (default)

Mode/config come from configs/default.toml (+ configs/local.toml), or from the options:

    python scripts/run_pipeline.py --mode integrated
    python scripts/run_pipeline.py --config configs/profiles/bodyparts3d.toml
    python scripts/run_pipeline.py --mode brainnetome --blender "E:/Programs/blender/blender.exe"
    python scripts/run_pipeline.py --mode integrated --skip-export        # reuse interim files, only rebuild the .blend
    python scripts/run_pipeline.py --mode integrated --dry-run            # print the commands only
    python scripts/run_pipeline.py --print-config                         # show the resolved settings

Blender executable: --blender, else [blender] executable in the config, else $BLENDER, else `blender`.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from medverse import settings  # noqa: E402

PIPELINE = _ROOT / "scripts" / "pipeline"
STEP_SCRIPTS = {
    "01": PIPELINE / "01_export_bodyparts3d.py",
    "02": PIPELINE / "02_export_bna_voxels.py",
    "03": PIPELINE / "03_integrate_brainnetome_bodyparts3d.py",
}


def build_commands(s, blender, skip_export=False, passthrough=()):
    """Return [(step, argv)] for the mode in `s` (a medverse.settings.Settings)."""
    extra = list(passthrough)
    cmds = []
    for step in s.steps:
        if step == "03":
            cmds.append((step, [blender, "--background", "--python", str(STEP_SCRIPTS[step]), "--", *extra]))
        elif not skip_export:
            cmds.append((step, [sys.executable, str(STEP_SCRIPTS[step]), *extra]))
    return cmds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=settings.MODES, help="what the final .blend contains")
    ap.add_argument("--config", help="TOML file or profile name (configs/profiles/<name>.toml)")
    ap.add_argument("--blender", help="path of the Blender executable")
    ap.add_argument("--skip-export", action="store_true", help="skip steps 01/02, only run the Blender step")
    ap.add_argument("--dry-run", action="store_true", help="print the commands without running them")
    ap.add_argument("--print-config", action="store_true", help="print the resolved settings and exit")
    args = ap.parse_args(argv)

    settings.configure(args.config, args.mode)
    s = settings.get()
    print(f"[pipeline] {s.describe()}")
    print(f"[pipeline] config files: {', '.join(str(p) for p in s.sources)}")
    if args.print_config:
        import json
        print(json.dumps(s.raw, indent=2))
        return 0

    blender = args.blender or s.raw["blender"]["executable"] or os.environ.get("BLENDER") or "blender"
    if "03" in s.steps and not args.dry_run and not shutil.which(blender) and not Path(blender).is_file():
        print(f"[pipeline] Blender not found: '{blender}'. Use --blender, [blender] executable or $BLENDER.",
              file=sys.stderr)
        return 2

    passthrough = []
    if args.mode:
        passthrough += ["--mode", args.mode]
    if args.config:
        passthrough += ["--config", args.config]
    for step, cmd in build_commands(s, blender, args.skip_export, passthrough):
        print(f"\n[pipeline] step {step}: {' '.join(cmd)}")
        if args.dry_run:
            continue
        rc = subprocess.call(cmd, cwd=_ROOT)
        if rc != 0:
            print(f"[pipeline] step {step} failed (exit code {rc}); stopping.", file=sys.stderr)
            return rc
    print("\n[pipeline] done" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

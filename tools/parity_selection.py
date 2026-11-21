"""Selection parity: NEW engine (profile legacy_parity) vs OLD classify_all on the same metadata.
Usage: python tools/parity_selection.py   (needs legacy/ next to src/)"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from medverse.config import load_config                       # noqa: E402
from medverse.adapters.bodyparts3d import BodyParts3DAdapter  # noqa: E402
from medverse.adapters.brainnetome import BrainnetomeAdapter   # noqa: E402
from medverse.selection.resolver import SelectionEngine       # noqa: E402


def run(meta_dir=None, profile="legacy_parity", verbose=True):
    meta_dir = Path(meta_dir or ROOT / "data/raw/bodyparts3d/metadata")
    out = Path(tempfile.mkdtemp()) / "legacy.json"
    env = dict(os.environ, MEDVERSE_ROOT=str(ROOT / "legacy"), MEDVERSE_DATA_DIR=str(ROOT / "data"),
               PYTHONPATH=str(ROOT / "legacy" / "src"))
    subprocess.run([sys.executable, str(ROOT / "tools" / "legacy_dump.py"), str(meta_dir), str(out)], env=env,
                   check=True, capture_output=True)
    old = json.load(open(out))
    cfg = load_config(root=ROOT, profile=profile,
                      overrides={"sources": {"bodyparts3d": {"metadata_dir": str(meta_dir)},
                                             "brainnetome": {"root": str(ROOT / "data/raw/brainnetome")}}})
    ad, bn = BodyParts3DAdapter(cfg), BrainnetomeAdapter(cfg)
    for a in (ad, bn):
        a.discover()
        a.build()
    srcs = {"bodyparts3d": (ad.entities, ad.ontology), "brainnetome": (bn.entities, bn.ontology)}
    dec = {d.entity_id.split(":")[1]: d for d in SelectionEngine(cfg, srcs).run() if d.source == "bodyparts3d"}
    mism, checked = [], 0
    for fj, (decision, group, sub, label, reason) in old["classified"].items():
        d = dec[fj]
        checked += 1
        if decision == "include":
            ok = d.decision == "included" and d.group == group
        elif decision == "ambiguous":
            ok = d.decision == "review"
        elif group == "CORTEX_DUPLICATE":
            ok = d.decision == "reference"            # BP3D cortex = registration reference, never imported
        else:                                          # muscle / disabled
            ok = d.decision == "excluded"
        if not ok:
            mism.append((fj, label, (decision, group), (d.decision, d.group, d.rule)))
    # everything the old code never classified must be excluded (out of scope / muscle) in the new engine
    leaked = [fj for fj, d in dec.items() if fj not in old["classified"] and d.decision in ("included", "review")]
    rep = {"old_classified": checked, "mismatches": mism, "new_included_not_in_old": leaked,
           "equivalent": not mism and not leaked}
    if verbose:
        print(json.dumps({k: (v if k != "mismatches" else v[:15]) for k, v in rep.items()}, indent=1))
    return rep


if __name__ == "__main__":
    sys.exit(0 if run()["equivalent"] else 1)

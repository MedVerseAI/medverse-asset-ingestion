"""Run the OLD classifier (legacy/) on the metadata and dump decisions as JSON (separate process).
MEDVERSE_ROOT=legacy PYTHONPATH=legacy/src python tools/legacy_dump.py <metadata_dir> <out.json>"""
import json
import sys

from medverse.anatomy import classes, helpers

meta_dir, out = sys.argv[1], sys.argv[2]
files = helpers.find_metadata_files(meta_dir, meta_dir)
meta = classes.Metadata(files)
muscle, _ = helpers.compute_muscle_elements(meta)
cls = helpers.classify_all(meta, muscle)
res = {fj: [r["decision"], r["group"], r["subgroup"], r["label"], r["reason"]] for fj, r in cls.items()}
json.dump({"classified": res, "muscle": sorted(muscle), "all": meta.all_fjs}, open(out, "w"))
print("legacy classified", len(res))

"""Report writers.  All of them are cheap and idempotent so the pipeline can call them after every stage."""
from __future__ import annotations

import csv
from pathlib import Path

from medverse.reporting.diagnostics import atomic_write_json

SELECTION_COLUMNS = ["entity_id", "source", "label", "side", "semantic_category", "semantic_subcategory", "scope",
                     "decision", "rule", "matched_target", "group", "fallback_used", "reason", "ontology_ids"]


def write_selection_review(path, decisions) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SELECTION_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for d in decisions:
            row = d.to_dict() if hasattr(d, "to_dict") else dict(d)
            row["ontology_ids"] = ";".join(row.get("ontology_ids") or [])
            w.writerow(row)
    tmp.replace(path)


class Reports:
    """Owner of the eight report files of a run."""
    NAMES = {
        "pipeline": "pipeline_report.json", "selection": "selection_review.csv", "assets": "asset_manifest.json",
        "transforms": "transform_manifest.json", "geometry": "geometry_report.json",
        "registration": "registration_report.json", "export": "export_report.json", "diagnostics": "diagnostics.log",
    }

    def __init__(self, out_dir):
        self.dir = Path(out_dir) / "reports"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.dir / self.NAMES[key]

    def json(self, key: str, obj) -> None:
        atomic_write_json(self.path(key), obj)

    def selection(self, decisions) -> None:
        write_selection_review(self.path("selection"), decisions)

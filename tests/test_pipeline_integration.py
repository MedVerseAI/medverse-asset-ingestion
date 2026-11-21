import json
import tempfile
from pathlib import Path

import numpy as np

import conftest  # noqa: F401
import synthetic
from medverse.config import load_config
from medverse.core import pipeline as P, registry
from medverse.core.pipeline import Pipeline


def _data(flip=False):
    d = tempfile.mkdtemp()
    synthetic.make_data(d, flip)
    return d


def _run(data, out, profile="brain_spine", **over):
    base = {"project": {"data_dir": data, "output_dir": out},
            "export": {"blend": {"enabled": False}, "fbx": {"enabled": False}},
            "blender": {"executable": ""}}
    for k, v in over.items():
        base.setdefault(k, {}).update(v)
    pl = Pipeline(load_config(profile=profile, overrides=base))
    return pl, pl.run()


def _rep(out, name):
    return json.loads((Path(out) / "reports" / name).read_text())


_CACHE = {}


def _e2e():
    if "r" not in _CACHE:
        data, out = _data(), tempfile.mkdtemp()
        pl, rc = _run(data, out)
        _CACHE["r"] = (data, out, pl, rc)
    return _CACHE["r"]


def test_all_reports_written_and_stage_contracts():
    data, out, pl, rc = _e2e()
    for f in ("pipeline_report.json", "selection_review.csv", "asset_manifest.json", "transform_manifest.json",
              "geometry_report.json", "registration_report.json", "diagnostics.log", "config_snapshot.json"):
        assert (Path(out) / "reports" / f).is_file(), f
    st = _rep(out, "pipeline_report.json")["stages"]
    assert list(st)[:3] == ["configuration", "discovery", "adapters"] and len(st) == 11
    assert st["selection"]["status"] == "ok" and st["registration"]["status"] == "ok"
    assert st["integration"]["outputs"]["objects"] > 100


def test_no_duplicates_and_cortex_owned_by_brainnetome():
    data, out, pl, rc = _e2e()
    inc = [d for d in pl.ctx.decisions if d.decision == "included"]
    cortex = {d.source for d in inc if d.semantic_category == "cerebral_cortex"}
    assert cortex == {"brainnetome"}
    assert pl.ctx.validation["selection"]["status"] in ("pass", "warn")
    assert not [c for c in pl.ctx.validation["selection"]["checks"] if c["status"] == "fail"]


def test_scale_never_applied_by_default_and_transforms_have_provenance():
    data, out, pl, rc = _e2e()
    t = _rep(out, "transform_manifest.json")
    assert t["scaled"] == []
    kinds = {r["kind"] for r in t["transforms"]}
    assert {"spatial_metadata", "unit_conversion", "frame_inference", "icp", "centering"} <= kinds
    assert all(r["reason"] for r in t["transforms"] if r["kind"] in ("unit_conversion", "frame_inference"))


def test_nifti_affine_preserved_and_atlas_frame_kept():
    data, out, pl, rc = _e2e()
    assert pl.ctx.volume_affine_ok == {"brainnetome": True}
    reg = pl.ctx.registration
    assert reg["moving"] == "bodyparts3d" and reg["fixed"] == "brainnetome"


def test_orientation_and_unit_validation_pass():
    data, out, pl, rc = _e2e()
    chk = {c["name"]: c["status"] for c in pl.ctx.validation["registration"]["checks"]}
    assert chk["orientation_left_right"] == "pass" and chk["units_mm"] == "pass"
    assert chk["nifti_affine_preserved:brainnetome"] == "pass"


def test_checksums_recorded():
    data, out, pl, rc = _e2e()
    a = _rep(out, "asset_manifest.json")
    assert all(len(f["sha256"]) == 64 for s in a["sources"].values() for f in s["discovery"]["files"])
    assert any(x["provenance"]["sha256"] for x in a["assets"])
    snap = _rep(out, "config_snapshot.json")
    assert len(snap["sha256"]) == 64


def test_scene_spec_organized_and_blender_missing_is_partial_not_crash():
    data, out, pl, rc = _e2e()
    spec = json.loads((Path(out) / "scene" / "spec.json").read_text())
    names = [o["name"] for o in spec["objects"]]
    assert len(names) == len(set(names))
    colls = {"/".join(c) for c in spec["collections"]}
    assert {"BRAIN", "SPINAL_SYSTEM", "BRAIN/CEREBRAL_CORTEX_BRAINNETOME/BN_LEFT_HEMISPHERE"} <= colls
    assert all((Path(out) / o["file"]).is_file() for o in spec["objects"])
    st = _rep(out, "pipeline_report.json")["stages"]
    assert st["integration"]["status"] == "partial"


def test_partial_failure_missing_source_is_isolated():
    data = _data()
    (Path(data) / "raw/brainnetome/atlas/BNA_MPM_thr25_1.25mm.nii.gz").unlink()
    out = tempfile.mkdtemp()
    pl, rc = _run(data, out)
    st = _rep(out, "pipeline_report.json")
    norm = st["stages"]["normalization"]
    assert norm["status"] == "partial"
    assert norm["per_source"]["brainnetome"]["status"] == "failed"
    assert norm["per_source"]["bodyparts3d"]["status"] == "ok"
    assert st["stages"]["geometry"]["per_source"]["bodyparts3d"]["meshes"] > 100
    assert st["stages"]["registration"]["status"] == "skipped"          # single surviving source
    assert (Path(out) / "reports" / "selection_review.csv").is_file()
    assert rc != 0


def test_reports_survive_a_crash_in_a_stage():
    data, out = _data(), tempfile.mkdtemp()
    orig = P.stage_registration

    def boom(ctx, res):
        raise RuntimeError("injected failure")
    P.STAGES[:] = [(n, boom if n == "registration" else f, r) for n, f, r in P.STAGES]
    try:
        pl, rc = _run(data, out)
    finally:
        P.STAGES[:] = [(n, orig if n == "registration" else f, r) for n, f, r in P.STAGES]
    rep = _rep(out, "pipeline_report.json")
    assert rep["stages"]["registration"]["status"] == "failed" and "injected" in rep["stages"]["registration"]["message"]
    assert rep["stages"]["integration"]["status"] == "skipped"        # dependants skipped with a reason
    assert rep["stages"]["geometry"]["status"] in ("ok", "partial")   # evidence of earlier stages kept
    assert (Path(out) / "reports" / "selection_review.csv").is_file() and rep["final"] is True
    assert "injected failure" in (Path(out) / "reports" / "diagnostics.log").read_text()


def test_lr_contradiction_is_mirrored_with_provenance():
    data, out = _data(flip=True), tempfile.mkdtemp()
    pl, rc = _run(data, out)
    kinds = [r.kind for r in pl.ctx.tlog.records]
    assert "mirror" in kinds
    chk = {c["name"]: c["status"] for c in pl.ctx.validation["registration"]["checks"]}
    assert chk["orientation_left_right"] == "pass"           # after the recorded mirror, labels agree with x


def test_new_source_without_touching_core():
    """A brand-new adapter registers itself; selection runs without any core change."""
    from medverse.adapters.base import SourceAdapter
    from medverse.core.assets import SourceEntity

    @registry.register_adapter("dummy_dicom")
    class Dummy(SourceAdapter):
        def discover(self):
            return {"available": True, "files": [], "problems": []}

        def build(self):
            self.entities["dummy_dicom:1"] = SourceEntity("dummy_dicom:1", "dummy_dicom", "pons", frozenset({"pons", "brain"}),
                                                          frozenset({"pons"}))
            self.ontology.name["1"] = "pons"
            self.ontology.finalize()

        def load(self, e):
            raise NotImplementedError

    assert "dummy_dicom" in registry.adapters()
    from medverse.selection.resolver import SelectionEngine
    cfg = load_config(profile="brain_spine")
    ad = Dummy.__new__(Dummy)
    SourceAdapter.__init__(ad, dict(cfg, sources=dict(cfg["sources"], dummy_dicom={"enabled": True})))
    ad.build()
    d = SelectionEngine(cfg, {"dummy_dicom": (ad.entities, ad.ontology)}).run()[0]
    assert d.entity_id == "dummy_dicom:1"            # unknown source = no semantic rules -> out of scope, no crash

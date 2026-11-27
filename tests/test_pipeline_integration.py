import json
from pathlib import Path

import pytest

import conftest  # noqa: F401
import synthetic
from medverse import cli
from medverse.config import load_config
from medverse.core import pipeline as P, registry
from medverse.core.pipeline import Pipeline


def _make_data(base_dir: Path, flip: bool = False) -> str:
    d = base_dir / ("data_flip" if flip else "data")
    d.mkdir(parents=True, exist_ok=True)
    synthetic.make_data(str(d), flip)
    return str(d)


def _run(data: str, out: str, profile: str = "brain_spine", **over):
    base = {
        "project": {"data_dir": data, "output_dir": out},
        "export": {"blend": {"enabled": False}, "fbx": {"enabled": False}, "glb": {"enabled": False}},
        "blender": {"executable": ""},
    }
    for k, v in over.items():
        base.setdefault(k, {}).update(v)
    pl = Pipeline(load_config(profile=profile, overrides=base))
    return pl, pl.run()


def _rep(out, name):
    return json.loads((Path(out) / "reports" / name).read_text())


@pytest.fixture(scope="module")
def e2e_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("medverse_e2e")
    data = _make_data(root)
    out = str(root / "out")
    pl, rc = _run(data, out)
    return data, out, pl, rc


def test_all_reports_written_and_stage_contracts(e2e_run):
    data, out, pl, rc = e2e_run
    for f in ("pipeline_report.json", "selection_review.csv", "asset_manifest.json", "manifest.json",
              "transform_manifest.json", "geometry_report.json", "registration_report.json",
              "diagnostics.log", "config_snapshot.json"):
        assert (Path(out) / "reports" / f).is_file(), f
    assert (Path(out) / "final" / "manifest.json").is_file()
    st = _rep(out, "pipeline_report.json")["stages"]
    assert list(st)[:3] == ["configuration", "discovery", "adapters"] and len(st) == 11
    assert st["selection"]["status"] == "ok" and st["registration"]["status"] == "ok"
    assert st["integration"]["outputs"]["objects"] > 100


def test_no_duplicates_and_cortex_owned_by_brainnetome(e2e_run):
    data, out, pl, rc = e2e_run
    inc = [d for d in pl.ctx.decisions if d.decision == "included"]
    cortex = {d.source for d in inc if d.semantic_category == "cerebral_cortex"}
    assert cortex == {"brainnetome"}
    assert pl.ctx.validation["selection"]["status"] in ("pass", "warn")
    assert not [c for c in pl.ctx.validation["selection"]["checks"] if c["status"] == "fail"]


def test_scale_never_applied_by_default_and_transforms_have_provenance(e2e_run):
    data, out, pl, rc = e2e_run
    t = _rep(out, "transform_manifest.json")
    assert t["scaled"] == []
    kinds = {r["kind"] for r in t["transforms"]}
    assert {"spatial_metadata", "unit_conversion", "frame_inference", "icp", "centering"} <= kinds
    assert all(r["reason"] for r in t["transforms"] if r["kind"] in ("unit_conversion", "frame_inference"))


def test_nifti_affine_preserved_and_atlas_frame_kept(e2e_run):
    data, out, pl, rc = e2e_run
    assert pl.ctx.volume_affine_ok == {"brainnetome": True}
    reg = pl.ctx.registration
    assert reg["moving"] == "bodyparts3d" and reg["fixed"] == "brainnetome"


def test_orientation_and_unit_validation_pass(e2e_run):
    data, out, pl, rc = e2e_run
    chk = {c["name"]: c["status"] for c in pl.ctx.validation["registration"]["checks"]}
    assert chk["orientation_left_right"] == "pass" and chk["units_mm"] == "pass"
    assert chk["nifti_affine_preserved:brainnetome"] == "pass"


def test_checksums_recorded_and_all_brainnetome_assets_untruncated(e2e_run):
    data, out, pl, rc = e2e_run
    a = _rep(out, "asset_manifest.json")
    assert all(len(f["sha256"]) == 64 for s in a["sources"].values() for f in s["discovery"]["files"])
    assert any(x["provenance"]["sha256"] for x in a["assets"])
    # No [:1] truncation on Brainnetome volume assets!
    bn_assets = [x for x in a["assets"] if x["source"] == "brainnetome"]
    assert len(bn_assets) > 10
    snap = _rep(out, "config_snapshot.json")
    assert len(snap["sha256"]) == 64
    # Canonical manifest preserves all included entities
    canon = json.loads((Path(out) / "final" / "manifest.json").read_text())
    assert canon["summary"]["total_entities"] > 100
    assert any(e["source"] == "brainnetome" and "bn_region_id" in e for e in canon["entities"])


def test_scene_spec_organized_shared_metadata_and_blender_missing_is_partial(e2e_run):
    data, out, pl, rc = e2e_run
    spec = json.loads((Path(out) / "scene" / "spec.json").read_text())
    names = [o["name"] for o in spec["objects"]]
    assert len(names) == len(set(names))
    colls = {"/".join(c) for c in spec["collections"]}
    assert {"BRAIN", "SPINAL_SYSTEM", "BRAIN/CEREBRAL_CORTEX_BRAINNETOME/BN_LEFT_HEMISPHERE"} <= colls
    assert all((Path(out) / o["file"]).is_file() for o in spec["objects"])
    # Unified metadata contract: canonical keys + backward-compatible viewer aliases
    bn_obj = next(o for o in spec["objects"] if o["props"]["source"] == "Human Brainnetome")
    assert {"group", "side", "label", "bp3d_group", "hemisphere", "bn_region_id", "bn_region_name"} <= set(bn_obj["props"])
    bp_obj = next(o for o in spec["objects"] if o["props"]["source"] == "BodyParts3D")
    assert bp_obj["props"]["group"] == bp_obj["props"]["bp3d_group"]
    st = _rep(out, "pipeline_report.json")["stages"]
    assert st["integration"]["status"] == "partial"


def test_quest3_profile_consolidates_materials_and_respects_budget(tmp_path):
    data = _make_data(tmp_path)
    out = str(tmp_path / "out_q3")
    pl, rc = _run(data, out, profile="quest3_lod0")
    spec = json.loads((Path(out) / "scene" / "spec.json").read_text())
    assert spec["material_mode"] == "lobe_palette"
    assert spec["material_count"] <= 20
    canon = json.loads((Path(out) / "final" / "manifest.json").read_text())
    assert canon["summary"]["total_triangles"] < 180000
    assert canon["summary"]["within_quest3_budget"] is True


def test_cli_selection_does_not_mutate_global_stages(tmp_path):
    data = _make_data(tmp_path)
    out = str(tmp_path / "out_sel")
    before = list(P.STAGES)
    rc = cli.main(["selection", "--data", data, "--out", out])
    assert rc == 0
    assert P.STAGES == before  # global STAGES list untouched!


def test_partial_failure_missing_source_is_isolated(tmp_path):
    data = _make_data(tmp_path)
    (Path(data) / "raw/brainnetome/atlas/BNA_MPM_thr25_1.25mm.nii.gz").unlink()
    out = str(tmp_path / "out")
    pl, rc = _run(data, out)
    st = _rep(out, "pipeline_report.json")
    norm = st["stages"]["normalization"]
    assert norm["status"] == "partial"
    assert norm["per_source"]["brainnetome"]["status"] == "failed"
    assert norm["per_source"]["bodyparts3d"]["status"] == "ok"
    assert st["stages"]["geometry"]["per_source"]["bodyparts3d"]["meshes"] >= 50
    assert st["stages"]["registration"]["status"] == "skipped"          # single surviving source
    assert (Path(out) / "reports" / "selection_review.csv").is_file()
    assert rc != 0


def test_reports_survive_a_crash_in_a_stage(tmp_path):
    data = _make_data(tmp_path)
    out = str(tmp_path / "out")

    def boom(ctx, res):
        raise RuntimeError("injected failure")

    custom_stages = [(n, boom if n == "registration" else f, r) for n, f, r in P.STAGES]
    cfg = load_config(profile="brain_spine", overrides={
        "project": {"data_dir": data, "output_dir": out},
        "export": {"blend": {"enabled": False}, "fbx": {"enabled": False}, "glb": {"enabled": False}},
        "blender": {"executable": ""},
    })
    pl = Pipeline(cfg, stages=custom_stages)
    pl.run()
    rep = _rep(out, "pipeline_report.json")
    assert rep["stages"]["registration"]["status"] == "failed" and "injected" in rep["stages"]["registration"]["message"]
    assert rep["stages"]["integration"]["status"] == "skipped"        # dependants skipped with a reason
    assert rep["stages"]["geometry"]["status"] in ("ok", "partial")   # evidence of earlier stages kept
    assert (Path(out) / "reports" / "selection_review.csv").is_file() and rep["final"] is True
    assert "injected failure" in (Path(out) / "reports" / "diagnostics.log").read_text()


def test_lr_contradiction_is_mirrored_with_provenance(tmp_path):
    data = _make_data(tmp_path, flip=True)
    out = str(tmp_path / "out")
    pl, rc = _run(data, out)
    kinds = [r.kind for r in pl.ctx.tlog.records]
    assert "mirror" in kinds
    chk = {c["name"]: c["status"] for c in pl.ctx.validation["registration"]["checks"]}
    assert chk["orientation_left_right"] == "pass"           # after the recorded mirror, labels agree with x


def test_new_source_without_touching_core():
    """A brand-new adapter registers itself; load_config() + selection run without any core change."""
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
    cfg = load_config(profile="brain_spine", overrides={"sources": {"dummy_dicom": {"enabled": True}}})
    ad = Dummy(cfg)
    ad.build()
    d = SelectionEngine(cfg, {"dummy_dicom": (ad.entities, ad.ontology)}).run()[0]
    assert d.entity_id == "dummy_dicom:1"            # unknown source = no semantic rules -> out of scope, no crash

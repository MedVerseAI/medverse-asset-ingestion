"""Pipeline orchestration -- 11 stages, explicit contracts, failure-safe reporting.

 1 configuration   2 discovery   3 adapters   4 selection   5 normalization   6 geometry
 7 registration    8 integration 9 validation 10 export     11 reporting

Each stage reads/writes the shared Context.  A stage failure never deletes evidence: reports are flushed after every
stage and again in `finally`; dependants are marked `skipped` with the reason, independent stages still run.
"""
from __future__ import annotations

import collections
import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from medverse import __version__
from medverse.config import snapshot
from medverse.core import registry
from medverse.core.transforms import TransformLog, rigid
from medverse.reporting.diagnostics import Diagnostics
from medverse.reporting.manifest import Reports


class StageFailure(RuntimeError):
    pass


@dataclass
class StageResult:
    name: str
    status: str = "pending"            # pending | ok | partial | failed | skipped
    seconds: float = 0.0
    message: str = ""
    per_source: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class Context:
    cfg: dict
    out_dir: Path
    diag: Diagnostics
    reports: Reports
    tlog: TransformLog = field(default_factory=TransformLog)
    adapters: dict = field(default_factory=dict)
    discovery: dict = field(default_factory=dict)
    sources_active: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    selection_summary: dict = field(default_factory=dict)
    assets: dict = field(default_factory=dict)          # entity_id -> loaded asset (volume or mesh)
    meshes: dict = field(default_factory=dict)          # entity_id -> MeshAsset (processed)
    geometry_info: dict = field(default_factory=dict)
    frame_info: dict = field(default_factory=dict)
    registration: dict = None
    volume_info: dict = field(default_factory=dict)
    volume_affine_ok: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    spec_path: Path = None
    work_blend: Path = None
    integration: dict = field(default_factory=dict)
    exports: dict = field(default_factory=dict)
    stages: dict = field(default_factory=collections.OrderedDict)

    def dec(self) -> dict:
        return {d.entity_id: d for d in self.decisions}


# ====================================================================================================== stages
def stage_configuration(ctx: Context, res: StageResult):
    snap = snapshot(ctx.cfg)
    from medverse.reporting.diagnostics import atomic_write_json
    atomic_write_json(ctx.out_dir / "reports" / "config_snapshot.json", snap)
    res.outputs = {"config_sha256": snap["sha256"], "layers": ctx.cfg["_runtime"]["layers"],
                   "profile": ctx.cfg["profile"]["name"]}


def stage_discovery(ctx: Context, res: StageResult):
    for name, scfg in ctx.cfg["sources"].items():
        if not scfg["enabled"]:
            res.per_source[name] = {"status": "skipped", "detail": "disabled"}
            continue
        try:
            ad = registry.adapter_class(name)(ctx.cfg)
            d = ad.discover()
            ctx.discovery[name] = d
            for p in d.get("problems", []):
                ctx.diag.warn(f"{name}: {p}", "discovery")
            if d["available"]:
                ctx.adapters[name] = ad
                res.per_source[name] = {"status": "ok", "files": len(d.get("files", []))}
            else:
                res.per_source[name] = {"status": "failed", "detail": "; ".join(d.get("problems", []))}
        except Exception as exc:                                           # noqa: BLE001
            res.per_source[name] = {"status": "failed", "detail": str(exc)}
            ctx.diag.error(f"{name}: discovery failed: {exc}", "discovery", exc)
    if not ctx.adapters:
        raise StageFailure("no source is available")


def stage_adapters(ctx: Context, res: StageResult):
    for name in list(ctx.adapters):
        try:
            ctx.adapters[name].build()
            for p in ctx.adapters[name].problems:
                ctx.diag.warn(f"{name}: {p}", "adapters")
            res.per_source[name] = {"status": "ok", "entities": len(ctx.adapters[name].entities)}
            ctx.sources_active.append(name)
        except Exception as exc:                                           # noqa: BLE001
            res.per_source[name] = {"status": "failed", "detail": str(exc)}
            ctx.diag.error(f"{name}: adapter build failed: {exc}", "adapters", exc)
            ctx.adapters.pop(name)
    if not ctx.sources_active:
        raise StageFailure("no adapter could read its source")


def stage_selection(ctx: Context, res: StageResult):
    from medverse.selection.resolver import SelectionEngine, summarize
    eng = SelectionEngine(ctx.cfg, {n: (ctx.adapters[n].entities, ctx.adapters[n].ontology)
                                    for n in ctx.sources_active})
    ctx.decisions = eng.run()
    ctx.selection_summary = summarize(ctx.decisions)
    ctx.reports.selection(ctx.decisions)
    res.outputs = ctx.selection_summary
    for n in ctx.sources_active:
        res.per_source[n] = {"status": "ok", **ctx.selection_summary["by_source"].get(n, {})}
    rev = ctx.selection_summary["by_decision"].get("review", 0)
    if rev:
        ctx.diag.warn(f"{rev} structure(s) need review (selection_review.csv); none were included automatically",
                      "selection")


def stage_normalization(ctx: Context, res: StageResult):
    from medverse.geometry.normalization import frame_matrices, infer_frame
    from medverse.core.assets import MeshAsset
    want = collections.defaultdict(list)
    for d in ctx.decisions:
        if d.decision in ("included", "reference"):
            want[d.source].append(d)
    for src, decs in want.items():
        ad = ctx.adapters[src]
        missing, loaded = [], 0
        for d in decs:
            try:
                ctx.assets[d.entity_id] = ad.load(ad.entities[d.entity_id])
                loaded += 1
            except Exception as exc:                                       # noqa: BLE001
                missing.append({"entity_id": d.entity_id, "label": d.label, "error": str(exc)})
                ctx.diag.warn(f"{d.entity_id} ({d.label}): {exc}", "normalization")
        status = "ok" if not missing else ("partial" if loaded else "failed")
        res.per_source[src] = {"status": status, "loaded": loaded, "missing": missing[:50], "n_missing": len(missing)}
        try:
            for w in ad.validate_source():
                ctx.diag.warn(w, "normalization")
        except Exception as exc:                                           # noqa: BLE001
            res.per_source[src]["validate_error"] = str(exc)
            ctx.diag.warn(f"{src}: source validation skipped: {exc}", "normalization")
        if hasattr(ad, "volume_info"):
            ctx.volume_info[src] = ad.volume_info
            vols = [a for a in ctx.assets.values() if a.source == src and a.kind == "volume"]
            if vols:
                ctx.tlog.add(f"source:{src}", vols[0].affine, "spatial_metadata",
                             "NIfTI voxel->world affine preserved (never modified)",
                             {"orientation": ad.volume_info["orientation"], "voxel_size_mm": ad.volume_info["voxel_size_mm"]})
                ctx.volume_affine_ok[src] = bool(np.array_equal(vols[0].affine, np.asarray(ad.volume_info["affine"])))
        # raw meshes -> RAS mm (units + axes inferred from anatomy)
        raw = [a for a in ctx.assets.values() if a.source == src and a.kind == "mesh"
               and a.coordinate_system.name == "raw"]
        if raw:
            dec = ctx.dec()
            units = [{"points": a.vertices, "category": dec[a.asset_id].semantic_category,
                      "subcategory": dec[a.asset_id].semantic_subcategory, "side": dec[a.asset_id].side,
                      "names": sorted(ad.entities[a.asset_id].names)} for a in raw]
            info = infer_frame(units, ctx.cfg["geometry"])
            ctx.frame_info[src] = info
            for m in info["messages"]:
                ctx.diag.warn(f"{src} frame: {m}", "normalization")
            Tu, Ta = frame_matrices(info)
            ctx.tlog.add(f"source:{src}", Tu, "unit_conversion",
                         f"source units -> mm (factor {info['unit_factor_to_mm']}, from vertebral column length)",
                         {"vertebral_length_raw": info.get("vertebral_length_raw")})
            ctx.tlog.add(f"source:{src}", Ta, "frame_inference", "anatomical axes (R, A, S) inferred from landmarks",
                         {k: info.get(k) for k in ("confidence", "determinant", "raw_axis_angles_deg",
                                                   "worst_orthogonality_error_deg")})
            T = Ta @ Tu
            for a in raw:
                a.apply(T)
                a.coordinate_system.name, a.coordinate_system.units = "RAS", "mm"
                a.coordinate_system.inferred, a.coordinate_system.confidence = True, info["confidence"]
        if status == "failed":
            res.status = "partial"
    if not ctx.assets:
        raise StageFailure("no asset could be loaded")
    if any(v.get("n_missing") for v in res.per_source.values()):
        res.status = "partial"


def _decisions_of(ctx, source, kinds=("included", "reference")):
    return [d for d in ctx.decisions if d.source == source and d.decision in kinds and d.entity_id in ctx.assets]


def stage_geometry(ctx: Context, res: StageResult):
    from medverse.geometry import cleanup, extraction
    from medverse.core.assets import MeshAsset
    g = ctx.cfg["geometry"]
    gi = ctx.geometry_info = {"sources": {}, "skipped": [], "meshes": {}}
    for src in ctx.sources_active:
        decs = _decisions_of(ctx, src)
        if not decs:
            res.per_source[src] = {"status": "skipped", "detail": "nothing selected"}
            continue
        n_ok, n_skip = 0, 0
        for d in decs:
            a = ctx.assets[d.entity_id]
            try:
                if a.kind == "volume":                                    # extraction decided here, not in the core
                    scfg = ctx.cfg["sources"][src]
                    m = extraction.extract_region_surface(a, a.metadata["region_id"], scfg["smooth_sigma"],
                                                          scfg["min_voxels"])
                    m.metadata.update(label=d.label)
                elif a.kind == "mesh":
                    v, f, st = cleanup.clean_mesh(a.vertices, a.faces, g["weld_tolerance_mm"],
                                                  g["component_min_faces"], g["component_min_fraction"])
                    a.vertices, a.faces = v, f
                    if d.decision == "included":
                        budget = g["face_budget"].get(d.group, g["default_face_budget"])
                        v, f, dec, why = cleanup.decimate(v, f, budget, g["decimation_aggressiveness"],
                                                          g["max_bbox_drift_mm"])
                        a.vertices, a.faces = v, f
                        st["decimated"], st["decimation_note"] = dec, why
                    a.metadata.update(closed=st["closed"], stats=st)
                    m = a
                else:
                    raise ValueError(f"unsupported asset kind {a.kind}")
                m.metadata["closed"] = m.metadata.get("closed", cleanup.is_closed(m.faces))
                ctx.meshes[d.entity_id] = m
                gi["meshes"][d.entity_id] = {"vertices": int(len(m.vertices)), "faces": int(len(m.faces)),
                                             "closed": bool(m.metadata["closed"]),
                                             "stats": m.metadata.get("stats")}
                n_ok += 1
            except extraction.NoSurface as exc:
                gi["skipped"].append({"entity_id": d.entity_id, "reason": str(exc)})
                ctx.diag.warn(str(exc), "geometry")
                n_skip += 1
            except Exception as exc:                                       # noqa: BLE001
                gi["skipped"].append({"entity_id": d.entity_id, "reason": f"{type(exc).__name__}: {exc}"})
                ctx.diag.warn(f"{d.entity_id}: geometry failed: {exc}", "geometry")
                n_skip += 1
        res.per_source[src] = {"status": "ok" if not n_skip else "partial", "meshes": n_ok, "skipped": n_skip}
        # Brainnetome-style orientation policy (label side vs affine) -- recorded, never silent
        ad = ctx.adapters[src]
        if hasattr(ad, "lr_check"):
            lr = ad.volume_info["lr_check"] if hasattr(ad, "volume_info") else ad.lr_check()
            gi["sources"][src] = {"lr_check": lr}
            if lr.get("mismatch"):
                pol = ctx.cfg["sources"][src]["on_lr_mismatch"]
                msg = (f"{src}: left-labelled regions lie at +x (mean x L={lr['mean_x_left']:+.1f}, "
                       f"R={lr['mean_x_right']:+.1f}) -> label/affine contradiction")
                if pol == "fail":
                    raise StageFailure(msg)
                ctx.diag.warn(msg + f"; policy={pol}", "geometry")
                if pol == "mirror":
                    P = np.diag([-1.0, 1.0, 1.0, 1.0])
                    for d in _decisions_of(ctx, src):
                        if d.entity_id in ctx.meshes:
                            ctx.meshes[d.entity_id].apply(P)
                    ctx.tlog.add(f"source:{src}", P, "mirror", "left_right_label_contradiction: x -> -x", lr)
        gap = g["region_gap_scale"]
        if src == "brainnetome" and gap != 1.0:
            for d in _decisions_of(ctx, src, ("included",)):
                m = ctx.meshes.get(d.entity_id)
                if m is not None:
                    c = np.median(m.vertices, axis=0)
                    m.vertices = c + (m.vertices - c) * gap
            ctx.tlog.add(f"source:{src}", np.diag([gap] * 3 + [1.0]), "scale",
                         "visual gap between atlas regions (geometry.region_gap_scale), scaled about each region centre")
    if not ctx.meshes:
        raise StageFailure("no mesh survived geometry processing")
    if gi["skipped"]:
        res.status = "partial"
    res.outputs = {"meshes": len(ctx.meshes), "skipped": len(gi["skipped"])}


def compute_landmarks(ctx: Context) -> dict:
    """{source: {key_side: bbox centre (mm)}} from the processed meshes (selection categories drive it)."""
    import re
    lc = ctx.cfg["registration"]["landmarks"]
    dec = ctx.dec()
    out = {}
    for src in ctx.sources_active:
        rules = {k: re.compile(v) for k, v in lc.get(src, {}).items()}
        buckets = collections.defaultdict(list)
        for eid, m in ctx.meshes.items():
            d = dec[eid]
            if d.source != src or d.semantic_category not in lc["categories"]:
                continue
            for key, rx in rules.items():
                if rx.search(d.label.lower()):
                    buckets[f"{key}_{d.side or 'M'}"].append(m.vertices)
        out[src] = {k: (np.concatenate(v).min(0) + np.concatenate(v).max(0)) / 2.0 for k, v in buckets.items()}
    return out


def _cloud(ctx: Context, src: str, cats):
    dec = ctx.dec()
    arr = [m.vertices for e, m in ctx.meshes.items() if dec[e].source == src and dec[e].semantic_category in cats]
    if not arr:
        return None
    pts = np.concatenate(arr)
    n = ctx.cfg["geometry"]["reference_point_count"] * 4
    return pts[np.linspace(0, len(pts) - 1, min(n, len(pts))).astype(np.int64)]


def stage_registration(ctx: Context, res: StageResult):
    from medverse.geometry.registration import register
    rc = ctx.cfg["registration"]
    active = [s for s in ctx.sources_active if any(ctx.dec()[e].source == s for e in ctx.meshes)]
    if len(active) < 2:
        res.status, res.message = "skipped", "single-source model: no registration needed"
        ctx.registration = None
        return
    moving = rc["moving_source"]
    if moving not in active:
        raise StageFailure(f"moving source '{moving}' produced no geometry")
    fixed = [s for s in active if s != moving][0]
    lms = compute_landmarks(ctx)
    cats = rc["landmarks"]["reference_categories"]
    reg = register(_cloud(ctx, moving, cats), _cloud(ctx, fixed, cats), lms.get(moving, {}), lms.get(fixed, {}), rc)
    ctx.registration = dict(reg, moving=moving, fixed=fixed)
    T = reg["T"]
    for e, m in ctx.meshes.items():
        if m.source == moving:
            m.apply(T)
    ctx.tlog.add(f"source:{moving}", T, "icp" if any(s.get("stage") == "icp" and s.get("accepted") for s in reg["stages"])
                 else "landmark" if any(s.get("stage") == "landmarks" and s.get("accepted") for s in reg["stages"])
                 else "reference_geometry",
                 f"registration {moving} -> {fixed} ({reg['confidence']} confidence)",
                 {"stages": reg["stages"], **reg["diagnostics"]})
    if abs(reg["scale_used"] - 1.0) > 1e-9:
        ctx.tlog.add(f"source:{moving}", np.diag([reg["scale_used"]] * 3 + [1.0]), "scale", reg["scale_reason"])
    ctx.diag.info(f"registration {moving}->{fixed}: confidence={reg['confidence']} scale={reg['scale_used']:.4f} "
                  f"landmark RMS={reg['diagnostics']['landmark_rms_mm']}", "registration")
    if reg["confidence"] != "ok":
        ctx.diag.warn("registration confidence is LOW (no independent landmark validation)", "registration")
        if rc["fail_on_low_confidence"]:
            raise StageFailure("registration confidence low and fail_on_low_confidence = true")
    # world frame of the scene: the atlas keeps its own frame (NIfTI affine preserved)
    if ctx.cfg["scene"]["frame"] == "atlas":
        atlas = next((s for s in active if any(a.kind == "volume" and a.source == s for a in ctx.assets.values())), None)
        if atlas == moving:
            Tinv = np.linalg.inv(T)
            for m in ctx.meshes.values():
                m.apply(Tinv)
            ctx.tlog.add("scene", Tinv, "scene_frame", f"re-express the scene in the '{atlas}' atlas frame")
    res.outputs = {"confidence": reg["confidence"], "scale_used": reg["scale_used"]}
    res.per_source = {moving: {"status": "ok", "role": "moving"}, fixed: {"status": "ok", "role": "fixed"}}


def stage_integration(ctx: Context, res: StageResult):
    from medverse.scene import organization
    from medverse.reporting.diagnostics import atomic_write_json
    sc = ctx.cfg["scene"]
    dec = ctx.dec()
    inc = {e: m for e, m in ctx.meshes.items() if dec[e].decision == "included"}
    if not inc:
        raise StageFailure("no included mesh to integrate")
    basis = [m.vertices for e, m in inc.items() if sc["center_on"] != "cortex_bbox" or
             dec[e].semantic_category == "cerebral_cortex"] or [m.vertices for m in inc.values()]
    allv = np.concatenate(basis)
    center = (allv.min(0) + allv.max(0)) / 2.0
    C = rigid(t=-center)
    for m in inc.values():
        m.apply(C)
    ctx.tlog.add("scene", C, "centering", f"scene centred on {sc['center_on']}", {"shift_mm": (-center).tolist()})
    ctx.tlog.add("scene", np.diag([sc["units_per_mm"]] * 3 + [1.0]), "scene_units",
                 "mm -> Blender units (applied by the builder, geometry stays in mm)")
    # landmarks (helpers) in the final frame: recompute from reference-capable meshes + centering
    lm = {}
    for src, d in compute_landmarks(ctx).items():
        lm[src] = {k: v - 0 for k, v in d.items()}
    for src in lm:                                       # reference meshes were not centred -> apply C to the points
        lm[src] = {k: v + C[:3, 3] if not any(dec[e].source == src and dec[e].decision == "included" and
                                              dec[e].semantic_category in ctx.cfg["registration"]["landmarks"]["categories"]
                                              for e in inc) else v for k, v in lm[src].items()}
    out = Path(ctx.out_dir)
    spec = organization.build_spec(ctx.cfg, inc, dec, lm, out, {"center_mm": center.tolist(), "frame": sc["frame"]})
    ctx.spec_path = out / "scene" / "spec.json"
    atomic_write_json(ctx.spec_path, spec)
    res.outputs = {"objects": len(spec["objects"]), "collections": len(spec["collections"]),
                   "spec": str(ctx.spec_path)}
    ctx.integration = {"spec_objects": len(spec["objects"])}
    from medverse.exporters.blender import BlenderUnavailable, run_blender
    try:
        work = out / "work"
        r = run_blender(ctx.cfg, "build", {"spec_path": str(ctx.spec_path), "work_blend": str(work / "integrated_scene.blend")},
                        work, ctx.diag)
        ctx.integration["blender"] = r
        if r["status"] == "ok":
            ctx.work_blend = Path(r["blend"])
        else:
            res.status, res.message = "partial", f"Blender build failed: {r.get('error')}"
    except BlenderUnavailable as exc:
        res.status, res.message = "partial", f"{exc}; scene spec was written, Blender scene not built"
        ctx.diag.warn(res.message, "integration")
        ctx.integration["blender"] = {"status": "skipped", "reason": str(exc)}


def stage_validation(ctx: Context, res: StageResult):
    from medverse.validation.geometry import validate_geometry
    from medverse.validation.registration import validate_registration
    from medverse.validation.selection import validate_selection
    dec = ctx.dec()
    inc = {e: m for e, m in ctx.meshes.items() if dec[e].decision == "included"}
    ctx.validation["selection"] = validate_selection(ctx.decisions, ctx.cfg,
                                                     sum(len(ctx.adapters[s].entities) for s in ctx.sources_active))
    ctx.validation["geometry"] = validate_geometry(inc)
    vol_checks = {f"nifti_affine_preserved:{s}": ok for s, ok in ctx.volume_affine_ok.items()}
    ctx.validation["registration"] = validate_registration(ctx.registration, ctx.cfg, inc, dec, vol_checks)
    bl = ctx.integration.get("blender", {})
    if bl.get("status") == "ok":
        ctx.validation["blender_scene"] = {"status": "pass" if bl["meshes"] == len(inc) else "fail",
                                           "meshes": bl["meshes"], "expected": len(inc)}
    states = [v["status"] for v in ctx.validation.values()]
    res.outputs = {k: v["status"] for k, v in ctx.validation.items()}
    for k, v in ctx.validation.items():
        for c in v.get("checks", []):
            if c["status"] == "fail":
                ctx.diag.error(f"validation[{k}] {c['name']}: {c['detail']}", "validation")
            elif c["status"] == "warn":
                ctx.diag.warn(f"validation[{k}] {c['name']}: {c['detail']}", "validation")
    if "fail" in states:
        res.status, res.message = "partial", "validation failures (see reports)"


def stage_export(ctx: Context, res: StageResult):
    for name, fn in registry.exporters().items():
        try:
            r = fn(ctx)
        except Exception as exc:                                           # noqa: BLE001
            r = {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}
            ctx.diag.error(f"export {name}: {exc}", "export", exc)
        ctx.exports[name] = r
        res.per_source[name] = {"status": r["status"], "detail": r.get("error") or r.get("reason", "")}
    bad = [n for n, r in ctx.exports.items() if r["status"] not in ("ok", "skipped")]
    if bad:
        res.status = "failed" if len(bad) == len(ctx.exports) else "partial"
        res.message = f"export failed: {bad}"


def stage_reporting(ctx: Context, res: StageResult):
    ctx.flush(final=True)


STAGES = [  # (name, function, requires)
    ("configuration", stage_configuration, []),
    ("discovery", stage_discovery, ["configuration"]),
    ("adapters", stage_adapters, ["discovery"]),
    ("selection", stage_selection, ["adapters"]),
    ("normalization", stage_normalization, ["selection"]),
    ("geometry", stage_geometry, ["normalization"]),
    ("registration", stage_registration, ["geometry"]),
    ("integration", stage_integration, ["geometry", "registration"]),
    ("validation", stage_validation, ["geometry"]),
    ("export", stage_export, ["integration"]),
    ("reporting", stage_reporting, []),
]


class Pipeline:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        out = Path(cfg["_runtime"]["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        self.ctx = Context(cfg=cfg, out_dir=out, diag=Diagnostics(out / "reports"), reports=Reports(out))
        self.ctx.flush = self._flush

    # --------------------------------------------------------------------------------------------- reporting
    def _flush(self, final: bool = False):
        c = self.ctx
        R = c.reports
        stages = {k: v.to_dict() for k, v in c.stages.items()}
        sts = [v["status"] for k, v in stages.items() if k != "reporting"]
        overall = ("failed" if any(s == "failed" for s in sts) else
                   "partial" if any(s in ("partial", "skipped") for s in sts) else
                   "ok" if sts and all(s == "ok" for s in sts) else "running")
        if not final and overall == "ok":
            overall = "running"
        R.json("pipeline", {"version": __version__, "profile": self.cfg["profile"]["name"], "status": overall,
                            "final": final, "stages": stages, "validation": {k: v["status"] for k, v in c.validation.items()},
                            "warnings": c.diag.warnings, "errors": c.diag.errors,
                            "outputs": {"out_dir": str(c.out_dir)}})
        R.json("assets", {"sources": {n: {"discovery": {k: v for k, v in d.items()}, "entities":
                                          len(c.adapters[n].entities) if n in c.adapters else 0}
                                      for n, d in c.discovery.items()},
                          "assets": [a.manifest() for a in c.assets.values() if a.kind != "volume"][:5000] +
                                    [a.manifest() for a in list(c.assets.values()) if a.kind == "volume"][:1],
                          "volumes": c.volume_info})
        R.json("transforms", c.tlog.to_dict())
        if c.geometry_info:
            R.json("geometry", {"geometry": c.geometry_info, "frame_inference": c.frame_info,
                                "validation": c.validation.get("geometry")})
        if c.registration is not None or "registration" in c.validation:
            reg = c.registration or {}
            R.json("registration", {"result": {k: v for k, v in reg.items() if k != "T"},
                                    "T_moving_to_fixed": reg["T"].tolist() if "T" in reg else None,
                                    "validation": c.validation.get("registration")})
        if c.exports:
            R.json("export", {"exports": c.exports, "integration": c.integration})
        if c.decisions:
            R.selection(c.decisions)

    # --------------------------------------------------------------------------------------------- run
    def run(self) -> int:
        c = self.ctx
        c.diag.info(f"MedVerse {__version__} | profile={self.cfg['profile']['name']} | out={c.out_dir}", "pipeline")
        try:
            for name, fn, requires in STAGES:
                res = StageResult(name)
                c.stages[name] = res
                blocked = [r for r in requires if c.stages[r].status in ("failed", "skipped")
                           and not (name == "integration" and r == "registration" and c.stages[r].message.startswith("single"))]
                if blocked:
                    res.status, res.message = "skipped", f"upstream stage(s) not ok: {blocked}"
                    c.diag.warn(f"stage {name} skipped: {res.message}", name)
                    self._flush()
                    continue
                t0 = time.time()
                try:
                    c.diag.info(f"stage {name} ...", name)
                    fn(c, res)
                    if res.status == "pending":
                        res.status = "ok"
                except StageFailure as exc:
                    res.status, res.message = "failed", str(exc)
                    c.diag.error(str(exc), name)
                except Exception as exc:                                   # noqa: BLE001
                    res.status, res.message = "failed", f"{type(exc).__name__}: {exc}"
                    c.diag.error(f"stage {name} crashed: {exc}", name, exc)
                res.seconds = round(time.time() - t0, 3)
                c.diag.info(f"stage {name}: {res.status} ({res.seconds}s) {res.message}", name)
                if self.cfg["reporting"]["flush_after_each_stage"] and name != "reporting":
                    self._flush()
                if res.status == "failed" and self.cfg["project"]["stop_on_stage_failure"] and name != "reporting":
                    c.diag.warn("stop_on_stage_failure: stopping", name)
                    break
        finally:
            try:
                if "reporting" not in c.stages:
                    c.stages["reporting"] = StageResult("reporting", "ok")
                self._flush(final=True)
            except Exception as exc:                                       # noqa: BLE001
                c.diag.error(f"final report flush failed: {exc}", "reporting", exc)
        sts = [v.status for k, v in c.stages.items() if k != "reporting"]
        return 1 if "failed" in sts else 2 if any(s in ("partial", "skipped") for s in sts) else 0

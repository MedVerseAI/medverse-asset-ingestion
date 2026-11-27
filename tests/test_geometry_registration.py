import struct

import numpy as np
import pytest

import conftest  # noqa: F401
from medverse.adapters.brainnetome.nifti import _load_builtin, load_nifti, save_nifti
from medverse.config import load_config
from medverse.core.assets import MeshAsset, VolumeAsset
from medverse.core.transforms import rigid, rot_from_euler_deg
from medverse.geometry import cleanup, extraction
from medverse.geometry.registration import nearest, register, umeyama


def test_nifti_affine_roundtrip_exact(tmp_path):
    A = np.array([[-1.25, 0, 0, 90.0], [0, 1.25, 0, -126.0], [0, 0, 1.25, -72.0], [0, 0, 0, 1]])
    vol = np.random.default_rng(0).integers(0, 5, (7, 8, 9)).astype(np.int16)
    p = str(tmp_path / "a.nii.gz")
    save_nifti(p, vol, A)
    v2, A2 = load_nifti(p)
    assert np.array_equal(vol, v2) and np.allclose(A, A2)


def test_nifti_builtin_handles_vox_offset_zero(tmp_path):
    A = np.eye(4)
    vol = np.arange(8, dtype=np.int16).reshape((2, 2, 2))
    p = tmp_path / "legacy_zero_offset.nii"
    save_nifti(str(p), vol, A)
    raw = bytearray(p.read_bytes())
    struct.pack_into("<f", raw, 108, 0.0)  # simulate legacy vox_offset == 0 with magic n+1\0
    p.write_bytes(bytes(raw))
    v2, A2 = _load_builtin(str(p))
    assert np.array_equal(vol, v2) and np.allclose(A, A2)


def test_volume_orientation_and_extraction_uses_affine():
    A = np.array([[-2.0, 0, 0, 20.0], [0, 2.0, 0, -20.0], [0, 0, 2.0, -20.0], [0, 0, 0, 1]])
    data = np.zeros((20, 20, 20), np.int32)
    ii, jj, kk = np.indices(data.shape)
    data[(ii - 5) ** 2 + (jj - 10) ** 2 + (kk - 10) ** 2 < 16] = 7
    vol = VolumeAsset("v", "s", data=data, affine=A)
    assert vol.orientation() == "LAS"
    m = extraction.extract_region_surface(vol, 7, 0.8, 10)
    c = m.vertices.mean(0)
    assert np.allclose(c, (A @ np.array([5, 10, 10, 1]))[:3], atol=0.6)
    assert m.coordinate_system.units == "mm"


def test_volume_extraction_decimates_and_scene_budget_enforces_cap():
    A = np.eye(4)
    data = np.zeros((32, 32, 32), np.int32)
    ii, jj, kk = np.indices(data.shape)
    data[(ii - 16) ** 2 + (jj - 16) ** 2 + (kk - 16) ** 2 < 100] = 1
    vol = VolumeAsset("v:1", "brainnetome", data=data, affine=A)
    raw_m = extraction.extract_region_surface(vol, 1, 0.8, 10)
    dec_m = extraction.extract_region_surface(vol, 1, 0.8, 10, face_budget=200, max_bbox_drift_mm=2.5)
    assert len(raw_m.faces) > 500
    assert len(dec_m.faces) < len(raw_m.faces)

    # Test global scene budget enforcement across multiple meshes
    meshes = {
        "m1": MeshAsset("m1", "s", vertices=raw_m.vertices.copy(), faces=raw_m.faces.copy()),
        "m2": MeshAsset("m2", "s", vertices=raw_m.vertices.copy(), faces=raw_m.faces.copy()),
    }
    res = cleanup.enforce_scene_budget(meshes, ["m1", "m2"], scene_budget=600, min_faces_per_mesh=80)
    assert res["applied"] is True
    assert res["within_budget"] is True
    assert res["total_after"] <= 600


def test_extraction_skips_tiny_regions():
    A = np.eye(4)
    data = np.zeros((10, 10, 10), np.int32)
    data[3, 3, 3] = 4
    with pytest.raises(extraction.NoSurface):
        extraction.extract_region_surface(VolumeAsset("v", "s", data=data, affine=A), 4, 0.8, 10)


def test_clean_mesh_welds_and_closes():
    import synthetic
    v, f = synthetic.ellipsoid(np.zeros(3), np.array([10, 8, 6]))
    v2 = np.vstack([v, v[:5] + 1e-5])
    f2 = np.vstack([f, [[len(v), len(v) + 1, len(v) + 2]]])
    cv, cf, st = cleanup.clean_mesh(v2, f2, 1e-3)
    assert st["closed"] and cleanup.signed_volume(cv, cf) > 0 and len(cv) <= len(v) + 5


def _cloud():
    rng = np.random.default_rng(0)
    th, ph = rng.uniform(0, np.pi, 5000), rng.uniform(0, 2 * np.pi, 5000)
    return np.c_[70 * np.sin(th) * np.cos(ph), 90 * np.sin(th) * np.sin(ph), 60 * np.cos(th)]


def test_umeyama_zero_variance_guard_and_ckdtree_nearest():
    collapsed = np.ones((5, 3))
    with pytest.raises(ValueError, match="zero variance"):
        umeyama(collapsed, collapsed)
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 20.0, 0.0]])
    idx, dist = nearest(np.array([[9.5, 0.0, 0.0], [0.0, 19.0, 0.0]]), pts)
    assert idx.tolist() == [1, 2]
    assert np.allclose(dist, [0.5, 1.0])


def test_registration_recovers_rigid_with_landmarks_and_never_scales():
    P = _cloud()
    Tt = rigid(rot_from_euler_deg(6, -4, 9), [5, -8, 12])
    Q = P @ Tt[:3, :3].T + Tt[:3, 3]
    lm = {f"k{i}": P[i * 100] for i in range(6)}
    lmq = {k: v @ Tt[:3, :3].T + Tt[:3, 3] for k, v in lm.items()}
    r = register(P, Q, lm, lmq, load_config()["registration"])
    assert abs(r["scale_used"] - 1.0) < 1e-9 and np.abs(r["T"] - Tt).max() < 1e-6 and r["confidence"] == "ok"
    assert [s["stage"] for s in r["stages"]][:2] == ["spatial_metadata", "landmarks"]


def test_icp_centroid_shift_not_falsely_rejected_far_from_origin():
    """BodyParts3D meshes sit ~1,500 mm from origin; a 4 deg rotation shifts origin translation >100 mm
    but centroid displacement is tiny and must NOT be falsely rejected."""
    offset = np.array([0.0, 0.0, 1500.0])
    P = _cloud() + offset
    R = rot_from_euler_deg(0.0, 0.0, 4.0)
    c = P.mean(0)
    # Rotate around centroid + tiny 2 mm shift -> centroid shift = 2 mm, origin vector shift > 100 mm
    Q = (P - c) @ R.T + c + np.array([2.0, 0.0, 0.0])
    rc = load_config()["registration"]
    r = register(P, Q, {}, {}, rc)
    icp_stage = next(s for s in r["stages"] if s["stage"] == "icp")
    assert icp_stage["accepted"] is True, icp_stage
    assert icp_stage["translation_mm"] < 10.0


def test_registration_without_landmarks_uses_reference_geometry_and_icp_and_is_low_confidence():
    P = _cloud()
    Tt = rigid(rot_from_euler_deg(3, -2, 4), [4, -6, 8])
    Q = P @ Tt[:3, :3].T + Tt[:3, 3]
    r = register(P, Q, {}, {}, load_config()["registration"])
    assert r["confidence"] == "low" and abs(r["scale_used"] - 1.0) < 1e-9
    assert r["diagnostics"]["reference_rms_mm"] < 3.0
    assert any(s["stage"] == "icp" and s.get("accepted") for s in r["stages"])


def test_scale_only_with_reason_and_provenance():
    P = _cloud()
    Q = P * 1.1
    cfg = load_config(overrides={"registration": {"allow_scale": True, "scale_reason": "template vs individual size",
                                                  "scale_init": "fit_inside"}})["registration"]
    r = register(P, Q, {}, {}, cfg)
    assert abs(r["scale_used"] - 1.0) > 0.02 and r["scale_reason"]

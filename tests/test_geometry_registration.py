import tempfile
from pathlib import Path

import numpy as np

import conftest  # noqa: F401
from medverse.adapters.brainnetome.nifti import load_nifti, save_nifti
from medverse.config import load_config
from medverse.core.assets import VolumeAsset
from medverse.core.transforms import rigid, rot_from_euler_deg
from medverse.geometry import cleanup, extraction
from medverse.geometry.registration import register


def test_nifti_affine_roundtrip_exact():
    A = np.array([[-1.25, 0, 0, 90.0], [0, 1.25, 0, -126.0], [0, 0, 1.25, -72.0], [0, 0, 0, 1]])
    vol = np.random.default_rng(0).integers(0, 5, (7, 8, 9)).astype(np.int16)
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "a.nii.gz")
        save_nifti(p, vol, A)
        v2, A2 = load_nifti(p)
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
    assert np.allclose(c, A @ np.array([5, 10, 10, 1]) * 1.0 if False else (A @ np.array([5, 10, 10, 1]))[:3], atol=0.6)
    assert m.coordinate_system.units == "mm"


def test_extraction_skips_tiny_regions():
    A = np.eye(4)
    data = np.zeros((10, 10, 10), np.int32)
    data[3, 3, 3] = 4
    try:
        extraction.extract_region_surface(VolumeAsset("v", "s", data=data, affine=A), 4, 0.8, 10)
    except extraction.NoSurface:
        return
    raise AssertionError("expected NoSurface")


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


def test_registration_recovers_rigid_with_landmarks_and_never_scales():
    P = _cloud()
    Tt = rigid(rot_from_euler_deg(6, -4, 9), [5, -8, 12])
    Q = P @ Tt[:3, :3].T + Tt[:3, 3]
    lm = {f"k{i}": P[i * 100] for i in range(6)}
    lmq = {k: v @ Tt[:3, :3].T + Tt[:3, 3] for k, v in lm.items()}
    r = register(P, Q, lm, lmq, load_config()["registration"])
    assert abs(r["scale_used"] - 1.0) < 1e-9 and np.abs(r["T"] - Tt).max() < 1e-6 and r["confidence"] == "ok"
    assert [s["stage"] for s in r["stages"]][:2] == ["spatial_metadata", "landmarks"]


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

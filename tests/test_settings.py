import pytest

from medverse import settings
from medverse.settings import SettingsError


def _write(tmp_path, text, name="cfg.toml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_defaults_load_and_are_integrated():
    s = settings.load()
    assert s.mode == "integrated"
    assert s.use_brainnetome and s.use_bodyparts3d
    assert s.steps == ("01", "02", "03")
    assert not s.export_bp3d_cortex
    assert "CEREBRAL_CORTEX" not in s.bp3d_groups


@pytest.mark.parametrize("profile,bn,bp,steps,cortex", [
    ("brainnetome", True, False, ("02", "03"), False),
    ("bodyparts3d", False, True, ("01", "03"), True),
    ("integrated", True, True, ("01", "02", "03"), False),
])
def test_profiles(profile, bn, bp, steps, cortex):
    s = settings.load(config=profile)
    assert (s.use_brainnetome, s.use_bodyparts3d, s.steps, s.export_bp3d_cortex) == (bn, bp, steps, cortex)
    assert ("CEREBRAL_CORTEX" in s.bp3d_groups) == cortex


def test_mode_override_wins_over_config_file(tmp_path):
    cfg = _write(tmp_path, '[model]\nmode = "bodyparts3d"\n')
    assert settings.load(config=cfg).mode == "bodyparts3d"
    assert settings.load(config=cfg, mode="brainnetome").mode == "brainnetome"


def test_bodyparts3d_cortex_can_be_disabled(tmp_path):
    cfg = _write(tmp_path, '[model]\nmode = "bodyparts3d"\n[bodyparts3d]\ninclude_cortex = false\n')
    s = settings.load(config=cfg)
    assert not s.export_bp3d_cortex and "CEREBRAL_CORTEX" not in s.bp3d_groups


@pytest.mark.parametrize("text,msg", [
    ('[model]\nmode = "everything"\n', "must be one of"),
    ('[modle]\nmode = "integrated"\n', "unknown key"),
    ('[brainnetome]\nsmooth_sigma = "high"\n', "must be a number"),
    ('[brainnetome]\nregion_gap_scale = 5\n', "must be within"),
    ('[bodyparts3d]\nenabled_groups = ["BRAIN"]\n', "unknown group"),
    ('[bodyparts3d.face_budget]\nBRAIN = 10\n', "unknown group"),
    ('[viewport]\neuler_deg = [1, 2]\n', "must have 3 items"),
    ('[scene]\nclear_previous_model = 1\n', "true/false"),
])
def test_invalid_configs_are_rejected(tmp_path, text, msg):
    with pytest.raises(SettingsError, match=msg):
        settings.load(config=_write(tmp_path, text))


def test_missing_config_file():
    with pytest.raises(SettingsError, match="not found"):
        settings.load(config="no_such_profile")


def test_parse_argv_handles_blender_double_dash():
    argv = ["blender", "--background", "--python", "x.py", "--", "--mode", "brainnetome"]
    assert settings.parse_argv(argv).mode == "brainnetome"
    assert settings.parse_argv(["x.py", "--mode", "bodyparts3d", "--unknown"]).mode == "bodyparts3d"
    assert settings.parse_argv(["blender", "-b", "--python", "x.py"]).mode is None


def test_apply_maps_legacy_constants():
    ns = {}
    s = settings.load(config="brainnetome")
    settings.apply(ns, s)
    assert ns["MODE"] == "brainnetome" and ns["USE_BODYPARTS3D"] is False
    assert ns["BN_CORTICAL_MAX_ID"] == 210
    assert ns["REG_MANUAL_SCALE"] is None                      # 0 in TOML = automatic
    assert isinstance(ns["VIEW_EULER_DEG"], tuple)
    assert ns["FACE_BUDGET"]["CEREBRAL_CORTEX"] == 60000

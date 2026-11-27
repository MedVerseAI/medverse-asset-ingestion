import conftest  # noqa: F401
from medverse.config import ConfigError, load_config


def _raises(fn, exc=ConfigError):
    try:
        fn()
    except exc:
        return True
    return False


def test_all_profiles_load():
    for p in ("brain_spine", "legacy_parity", "quest3_lod0"):
        cfg = load_config(profile=p)
        assert cfg["profile"]["name"] == p and cfg["profile"]["targets"]


def test_quest3_profile_budget_and_materials():
    cfg = load_config(profile="quest3_lod0")
    assert 0 < cfg["geometry"]["scene_triangle_budget"] < 180000
    assert cfg["geometry"]["decimate_volumes"] is True
    assert cfg["scene"]["material_mode"] == "lobe_palette"
    assert cfg["export"]["glb"]["enabled"] is True


def test_scale_requires_reason():
    assert _raises(lambda: load_config(overrides={"registration": {"allow_scale": True}}))


def test_allow_scale_default_false():
    assert load_config(profile="brain_spine")["registration"]["allow_scale"] is False


def test_unknown_key_rejected():
    assert _raises(lambda: load_config(overrides={"registration": {"allow_sclae": True}}))
    assert _raises(lambda: load_config(overrides={"geometry": {"weld_tolerence_mm": 1}}))
    # Built-in sources remain strictly validated for typos
    assert _raises(lambda: load_config(overrides={"sources": {"brainnetome": {"smooth_sgima": 0.5}}}))


def test_dynamic_plugin_source_allowed_via_load_config():
    cfg = load_config(
        profile="brain_spine",
        overrides={"sources": {"custom_dicom": {"enabled": True, "root": "/tmp/custom", "display_name": "Custom"}}},
    )
    assert cfg["sources"]["custom_dicom"]["enabled"] is True


def test_unknown_policy_never_include():
    assert _raises(lambda: load_config(overrides={"selection": {"unknown_policy": "include"}}))


def test_wrong_type_rejected():
    assert _raises(lambda: load_config(overrides={"geometry": {"weld_tolerance_mm": "x"}}))


def test_intervertebral_disc_toggle_is_explicit():
    cfg = load_config(profile="brain_spine")
    assert cfg["anatomy"]["spine"]["include_intervertebral_discs"] is True

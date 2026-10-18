import importlib.util
import pathlib

import pytest

from medverse import settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_pipeline", ROOT / "scripts" / "run_pipeline.py")
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)


@pytest.mark.parametrize("mode,steps", [
    ("brainnetome", ["02", "03"]),
    ("bodyparts3d", ["01", "03"]),
    ("integrated", ["01", "02", "03"]),
])
def test_commands_per_mode(mode, steps):
    cmds = rp.build_commands(settings.load(mode=mode), "blender")
    assert [c[0] for c in cmds] == steps
    assert "--background" in cmds[-1][1]


def test_skip_export_keeps_only_blender_step():
    cmds = rp.build_commands(settings.load(mode="integrated"), "blender", skip_export=True,
                             passthrough=["--mode", "integrated"])
    assert [c[0] for c in cmds] == ["03"]
    assert cmds[0][1][-3:] == ["--", "--mode", "integrated"]


def test_dry_run_prints_and_succeeds(capsys):
    assert rp.main(["--mode", "brainnetome", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "step 02" in out and "step 03" in out and "step 01" not in out

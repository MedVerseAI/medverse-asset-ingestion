import ast
import pathlib

from medverse.anatomy import config
from medverse.anatomy.classes import Log, MeshIndex


def test_config_paths_come_from_paths_module():
    assert config.BN_NII_DIR == str(config.paths.BN_ATLAS)
    assert config.OBJ_SEARCH_DIR.endswith("bodyparts3d")            # interim, not raw
    assert "interim" in config.OBJ_SEARCH_DIR
    assert config.BN_MPM_PATH.endswith("BNA_MPM_thr25_1.25mm.nii.gz")


def test_no_duplicate_function_definitions_in_config():
    tree = ast.parse(pathlib.Path(config.__file__).read_text(encoding="utf-8"))
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(names) == len(set(names))


def test_check_functions_report_missing(monkeypatch, tmp_path):
    assert isinstance(config.check_inputs(), list)
    assert isinstance(config.check_integration_inputs(), list)


def test_log_save(tmp_path):
    log = Log()
    log("hello")
    out = tmp_path / "r.txt"
    log.save(str(out))
    assert out.read_text(encoding="utf-8").strip() == "hello"


def test_mesh_index_finds_obj(tmp_path):
    d = tmp_path / "obj_isa"
    d.mkdir()
    (d / "FJ1234.obj").write_text("v 0 0 0\n")
    idx = MeshIndex(str(tmp_path))
    assert idx.count == 1 and idx.find("fj1234")

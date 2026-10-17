from medverse import paths


def test_layout_is_consistent():
    assert paths.BN_RAW.name == "brainnetome"
    assert paths.RAW.parent == paths.DATA
    for p in (paths.BP3D_EXPORT_MANIFEST, paths.BN_PIECES_DIR, paths.FINAL_BLEND, paths.EXPORT_BNA_REPORT):
        assert paths.DATA in p.parents


def test_reports_share_one_folder():
    for p in (paths.EXPORT_BP3D_REPORT, paths.EXPORT_BNA_REPORT, paths.INTEGRATION_REPORT):
        assert p.parent == paths.REPORTS


def test_data_dir_override(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("MEDVERSE_DATA_DIR", str(tmp_path))
    try:
        importlib.reload(paths)
        assert paths.DATA == tmp_path.resolve()
        paths.ensure_output_dirs()
        assert paths.REPORTS.is_dir() and paths.BN_PIECES_DIR.is_dir()
    finally:
        monkeypatch.undo()
        importlib.reload(paths)

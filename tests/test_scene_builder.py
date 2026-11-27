import json
from pathlib import Path

import conftest  # noqa: F401
import fake_bpy
from test_pipeline_integration import _make_data, _run


def test_builder_creates_organized_scene_with_fake_bpy(tmp_path):
    data = _make_data(tmp_path)
    out = str(tmp_path / "out")
    pl, rc = _run(data, out)
    spec_path = Path(out) / "scene" / "spec.json"
    spec = json.loads(spec_path.read_text())
    state = fake_bpy.install()
    from medverse.scene import builder
    audit = builder.build_scene(spec, str(Path(out)))
    assert audit["objects"] == len(spec["objects"])
    root = state["bpy"].data.collections.get(spec["root_name"])
    assert root is not None
    meshes = builder.list_model_objects(spec["root_name"])
    assert len(meshes) == len(spec["objects"])
    o = meshes[0]
    assert o.get("source") and o.get("entity_id") and o.get("selection_rule")
    assert o.get("group") and o.get("bp3d_group") and o.get("label")
    # each separated object lives in exactly one collection under the root
    seen = [x.name for x in meshes]
    assert len(seen) == len(set(seen))
    # rebuilding does not duplicate (clear_previous_model)
    builder.build_scene(spec, str(Path(out)))
    assert len(builder.list_model_objects(spec["root_name"])) == len(spec["objects"])
    # headless viewport setup runs cleanly without crashing on fake_bpy
    builder.setup_viewport(spec)

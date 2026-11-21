import conftest  # noqa: F401
from medverse.config import load_config
from medverse.core.assets import SourceEntity
from medverse.selection.ontology import Ontology
from medverse.selection.resolver import SelectionEngine


def _src(source, items):
    ents, o = {}, Ontology()
    for local, label, names, attrs in items:
        eid = f"{source}:{local}"
        ents[eid] = SourceEntity(eid, source, label, frozenset(names), frozenset(names), (local,), "", attrs)
        o.name[local] = label
    o.name["VC"] = "vertebral column"
    for eid, e in ents.items():
        if "vertebral column" in e.names:
            o.elements["partof"]["VC"].add(eid)
    o.finalize()
    return ents, o


def _cfg(**over):
    base = {"sources": {"bodyparts3d": {"enabled": True}, "brainnetome": {"enabled": True}}}
    for k, v in over.items():
        base.setdefault(k, {}).update(v)
    return load_config(profile="brain_spine", overrides=base)


def _run(cfg, bp, bn=None):
    srcs = {"bodyparts3d": bp}
    if bn is not None:
        srcs["brainnetome"] = bn
    return {d.entity_id: d for d in SelectionEngine(cfg, srcs).run()}


def _bp(items):
    return _src("bodyparts3d", items)


def test_priority_exclusion_beats_inclusion_beats_semantic():
    cfg = _cfg(selection={"inclusions": [{"id": "inc", "source": "bodyparts3d", "kind": "name_regex",
                                          "regex": "cerebellum", "target": "cerebellum"}],
                          "exclusions": [{"id": "ex", "source": "bodyparts3d", "kind": "name_regex",
                                          "regex": "muscle|cerebellum x"}]})
    bp = _bp([("A", "cerebellum", ["cerebellum", "brain"], {}),
              ("B", "cerebellum x", ["cerebellum x", "cerebellum", "brain"], {})])
    d = _run(cfg, bp)
    assert d["bodyparts3d:A"].decision == "included" and d["bodyparts3d:A"].rule.startswith("explicit_inclusion")
    assert d["bodyparts3d:B"].decision == "excluded" and d["bodyparts3d:B"].rule.startswith("explicit_exclusion")


def test_semantic_include_and_group():
    d = _run(_cfg(), _bp([("A", "pons", ["pons", "brain"], {})]))["bodyparts3d:A"]
    assert (d.decision, d.group, d.semantic_subcategory, d.rule) == ("included", "BRAINSTEM", "pons",
                                                                     "include_semantic_target")


def test_unknown_goes_to_review_never_included():
    d = _run(_cfg(), _bp([("A", "weird thing", ["weird thing", "brain"], {})]))["bodyparts3d:A"]
    assert d.decision == "review" and d.rule == "unknown_policy_review"
    cfg = _cfg(selection={"unknown_policy": "exclude"})
    assert _run(cfg, _bp([("A", "weird thing", ["weird thing", "brain"], {})]))["bodyparts3d:A"].decision == "excluded"


def test_out_of_scope_is_excluded():
    d = _run(_cfg(), _bp([("A", "femur", ["femur"], {})]))["bodyparts3d:A"]
    assert d.decision == "excluded" and d.rule == "out_of_scope"


def test_name_fallback_is_flagged():
    cfg = _cfg(selection={"name_fallback": [{"source": "bodyparts3d", "regex": "^pons-like$", "category": "brainstem",
                                              "subcategory": "pons"}]})
    d = _run(cfg, _bp([("A", "pons-like", ["pons-like"], {})]))["bodyparts3d:A"]
    assert d.decision == "included" and d.fallback_used and d.rule.startswith("fallback:")


def test_ownership_no_duplicate_cortex():
    bp = _bp([("A", "left angular gyrus", ["left angular gyrus", "brain", "cerebral cortex"], {})])
    bn = _src("brainnetome", [("001", "A39c_L", ["a39c_l"], {"cortical": True})])
    d = _run(_cfg(), bp, bn)
    assert d["bodyparts3d:A"].decision == "reference" and d["bodyparts3d:A"].rule == "owned_by_other_source"
    assert d["brainnetome:001"].decision == "included" and d["brainnetome:001"].group == "CEREBRAL_CORTEX"


def test_fallback_owner_when_owner_disabled():
    bp = _bp([("A", "left angular gyrus", ["left angular gyrus", "brain", "cerebral cortex"], {})])
    cfg = _cfg(sources={"brainnetome": {"enabled": False}})
    d = _run(cfg, bp)["bodyparts3d:A"]
    assert d.decision == "included" and d.group == "CEREBRAL_CORTEX"


def test_disc_toggle_explicit():
    bp = _bp([("A", "disc", ["intervertebral disk", "vertebral column"], {})])
    cfg = _cfg(anatomy={"spine": {"include_intervertebral_discs": False}})
    d = _run(cfg, bp)["bodyparts3d:A"]
    assert d.decision == "excluded" and d.rule == "target_disabled"


def test_every_decision_has_provenance_fields():
    d = _run(_cfg(), _bp([("A", "pons", ["pons", "brain"], {})]))["bodyparts3d:A"]
    row = d.to_dict()
    for k in ("entity_id", "source", "semantic_category", "decision", "rule", "matched_target", "fallback_used"):
        assert k in row


def test_parity_with_legacy_on_real_metadata():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if not (root / "legacy").is_dir() or not (root / "data/raw/bodyparts3d/metadata").is_dir():
        return
    import parity_selection
    rep = parity_selection.run(verbose=False)
    assert rep["equivalent"], rep["mismatches"][:5]

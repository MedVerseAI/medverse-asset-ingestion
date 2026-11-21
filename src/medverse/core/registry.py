"""Adapter / exporter registry.  Adding a source = registering one adapter class; the core never changes."""
from __future__ import annotations

_ADAPTERS: dict = {}
_EXPORTERS: dict = {}


def register_adapter(name: str):
    def deco(cls):
        _ADAPTERS[name] = cls
        cls.name = name
        return cls
    return deco


def register_exporter(name: str):
    def deco(fn):
        _EXPORTERS[name] = fn
        return fn
    return deco


def adapter_class(name: str):
    _autoload()
    if name not in _ADAPTERS:
        raise KeyError(f"no adapter registered for source '{name}' (known: {sorted(_ADAPTERS)})")
    return _ADAPTERS[name]


def adapters() -> dict:
    _autoload()
    return dict(_ADAPTERS)


def exporters() -> dict:
    _autoload()
    return dict(_EXPORTERS)


def _autoload():
    import importlib
    for mod in ("medverse.adapters.bodyparts3d", "medverse.adapters.brainnetome",
                "medverse.exporters.blender", "medverse.exporters.fbx"):
        importlib.import_module(mod)
